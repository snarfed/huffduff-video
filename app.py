"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: http://youtu.be/6dyWlM4ej3Q
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import contextlib
import datetime
import logging
import os
import re
import ssl
from string import Template
import sys
import urllib

import boto
import boto.ec2.cloudwatch
import webob
import webob.exc
import youtube_dl

HTML_HEADER = """\
<!DOCTYPE html>
<html>
<head>
<title>huffduff-video</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="mobile-web-app-capable" content="yes">
</head>
<style> #progress span {display:none;}
        #progress span:last-of-type {display:inline;}
</style>
<body>
<!-- %s ; %s -->
<h1><a href="http://huffduff-video.snarfed.org/" target="_blank">huffduff-video</a></h1>
""" % (sys.version, ssl.OPENSSL_VERSION)
HTML_FOOTER = """\
</body>
</html>
"""

def read(filename):
  with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)) as f:
    return f.read().strip()

AWS_KEY_ID = read('aws_key_id')
AWS_SECRET_KEY = read('aws_secret_key')
S3_BUCKET = 'huffduff-video'
S3_BASE = 'https://%s.s3-us-west-2.amazonaws.com/' % S3_BUCKET

# ffmpeg on Ryan's laptop is installed in /usr/local/bin, so add it to PATH.
if '/usr/local/bin' not in os.environ['PATH']:
  os.environ['PATH'] += ':/usr/local/bin'


def application(environ, start_response):
  """Hand-rolled WSGI application so I can stream output.

  ...by returning a generator that yields the response body lines.
  """
  request = webob.Request(environ)
  headers = [('Content-Type', 'text/html')]

  # validate request
  if request.method not in ('GET', 'POST'):
    return webob.exc.HTTPMethodNotAllowed()(environ, start_response)

  url = request.params.get('url')
  if not url:
    return webob.exc.HTTPBadRequest('Missing required parameter: url')(
      environ, start_response)

  # check that our CPU credit balance isn't too low
  try:
    cloudwatch = boto.ec2.cloudwatch.connect_to_region(
      'us-west-2', aws_access_key_id=AWS_KEY_ID,
      aws_secret_access_key=AWS_SECRET_KEY)
    for metric in cloudwatch.list_metrics(metric_name='CPUCreditBalance'):
      if metric.name == 'CPUCreditBalance':
        stats = metric.query(datetime.datetime.now() - datetime.timedelta(minutes=10),
                             datetime.datetime.now(), ['Average'])
        if stats:
          credit = stats[-1].get('Average')
          if credit and credit <= 30:
            msg = "Sorry, we're too busy right now. Please try again later!"
            exc = webob.exc.HTTPServiceUnavailable(msg)
            exc.html_template_obj = Template(HTML_HEADER + msg + HTML_FOOTER)
            return exc(environ, start_response)
  except:
    logging.exception("Couldn't fetch CPU credit balance from CloudWatch!")

  write_fn = start_response('200 OK', headers)
  def write(line):
    write_fn(line.encode('utf-8'))

  def run():
    """Generator that does all the work and yields the response body lines.

    TODO: figure out how to catch and log stack traces when this function raises
    an exception. Currently the log only gets the exception message. Wrapping
    the call at the bottom in try/except doesn't work since it's a generator. :/
    """
    yield HTML_HEADER
    yield ('<div id="progress">\nFetching %s ...<br />' % url).encode('utf-8')

    # function to print out status while downloading
    def download_progress_hook(progress):
      status = progress.get('status')
      if status == 'finished':
        msg = '<br />Extracting audio (this can take a while)...\n'
      elif status == 'error':
        # we always get an 'error' progress when the video finishes downloading.
        # not sure why. ignore it.
        return
      elif status == 'downloading':
        p = lambda field: progress.get(field) or ''
        percent = float(p('_percent_str').strip('%') or '0')
        msg = ('<span><progress max="100" value="%s"></progress><br /> '
               '%s of %s at %s in %s...</span>\n' % (
                 percent, p('_downloaded_bytes_str'),
                 p('_total_bytes_str') or p('_total_bytes_estimate_str'),
                 p('_speed_str'), p('_eta_str')))
      else:
        msg = status + '<br />\n'
      write(msg)

    # fetch video info (resolves URL) to see if we've already downloaded it
    options = {
      'outtmpl': u'/tmp/%(webpage_url)s',
      'restrictfilenames': True,  # don't allow & or spaces in file names
      'updatetime': False,  # don't set output file mtime to video mtime
      'logger': logging,
      'logtostderr': True,
      'format': 'bestaudio/best',
      'noplaylist': True,
      'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
      }],
      'progress_hooks': [download_progress_hook],
    }
    ydl = youtube_dl.YoutubeDL(options)
    with handle_errors(write):
      info = ydl.extract_info(url, download=False)

    # prepare_filename() returns the video filename, not the postprocessed one,
    # so change the extension manually. the resulting filename will look like:
    #   '/tmp/https_-_www.youtube.com_watchv=6dyWlM4ej3Q.mp3'
    #
    # ext4 max filename length is 255 bytes, and huffduffer also silently
    # truncates URLs to 255 chars total, so truncate before that if necessary.
    filename_prefix = ydl.prepare_filename(info)[:245 - len(S3_BASE)]
    options['outtmpl'] = filename_prefix.replace('%', '%%') + '.%(ext)s'
    filename = filename_prefix + '.mp3'

    s3 = boto.connect_s3(aws_access_key_id=AWS_KEY_ID,
                         aws_secret_access_key=AWS_SECRET_KEY)
    bucket = s3.get_bucket(S3_BUCKET)
    # strip the filename's path, scheme, and leading www., mobile, or m.
    # the resulting S3 key will look like 'youtube.com_watchv=6dyWlM4ej3Q.mp3'
    s3_key = re.sub('^https?_-_((www|m|mobile|player).)?', '', os.path.basename(filename))
    key = bucket.get_key(s3_key, validate=False)

    if key.exists():
      yield 'Already downloaded! <br />\n'
    else:
      # download video and extract mp3
      yield 'Downloading...<br />\n'
      with handle_errors(write):
        youtube_dl.YoutubeDL(options).download([url])

      # upload to S3
      # http://docs.pythonboto.org/en/latest/s3_tut.html
      yield 'Uploading to S3...<br />\n'

      def upload_callback(sent, total):
        write('<span><progress max="100" value="%s"></progress><br /> '
              '%.2fMB of %.2fMB</span>\n' % (
                (sent * 100 / total), float(sent) / 1000000, float(total) / 1000000))

      key.set_contents_from_filename(filename, cb=upload_callback)
      key.make_public()
      os.remove(filename)

    # get metadata, specifically last_modified
    key = bucket.get_key(s3_key)
    # generate description
    description = info.get('description') or ''
    footer = """\
Original video: %s
Downloaded by http://huffduff-video.snarfed.org/ on %s
Available for 30 days after download""" % (url, key.last_modified)
    # last_modified format is RFC 7231, e.g. 'Fri, 22 Jul 2016 07:11:46 GMT'
    if description:
      footer = """

===
""" + footer

    max_len = 1500 - len(footer)
    if len(description) > max_len:
      description = description[:max_len] + '...'
    description += footer

    # open 'Huffduff it' page
    yield """\n<br />Opening Huffduffer dialog...
<script type="text/javascript">
window.location = "https://huffduffer.com/add?popup=true&%s";
</script>
""" % urllib.urlencode([(k, v.encode('utf-8')) for k, v in
      (('bookmark[url]', (S3_BASE + s3_key)),
       ('bookmark[title]', info.get('title') or ''),
       ('bookmark[description]', description),
       ('bookmark[tags]', ','.join(info.get('categories') or [])),
     )])
    yield HTML_FOOTER

    # alternative:
    # http://themindfulbit.com/blog/optimizing-your-podcast-site-for-huffduffer

  return run()


@contextlib.contextmanager
def handle_errors(write):
  """Wraps youtube_dl calls in a try/except and handles errors."""
  try:
    yield
  except Exception, e:
    write('<p>%s</p>\n' % e)
    if isinstance(e, (youtube_dl.DownloadError, youtube_dl.utils.ExtractorError)):
      write("""\
Here are the <a href="http://rg3.github.io/youtube-dl/supportedsites.html">
supported sites</a>. If this site isn't supported, it may also post
its videos on YouTube. Try there!
""")
    write(HTML_FOOTER)
    raise
