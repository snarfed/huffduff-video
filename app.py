"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: http://youtu.be/6dyWlM4ej3Q
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import contextlib
import logging
import os
import re
import urllib

import boto
import webob
import webob.exc
import youtube_dl


def read(filename):
  with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)) as f:
    return f.read().strip()

AWS_KEY_ID = read('aws_key_id')
AWS_SECRET_KEY = read('aws_secret_key')
S3_BUCKET = 'huffduff-video'
S3_BASE = 'https://%s.s3-us-west-2.amazonaws.com/' % S3_BUCKET


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

  write_fn = start_response('200 OK', headers)
  def write(line):
    write_fn(line.encode('utf-8'))

  def run():
    """Generator that does all the work and yields the response body lines.

    TODO: figure out how to catch and log stack traces when this function raises
    an exception. Currently the log only gets the exception message. Wrapping
    the call at the bottom in try/except doesn't work since it's a generator. :/
    """
    yield ("""\
<!DOCTYPE html>
<html>
<head><title>huffduff-video: %s</title></head>
<style> #progress span {display:none;}
        #progress span:last-of-type {display:inline;}
</style>
<script type="text/javascript">
window.setInterval(function() { window.scrollTo(0, document.body.scrollHeight); }, 500);
</script>
<body>
<h1>huffduff-video</h1>
<div id="progress">
Fetching %s ...<br />""" % (url, url)).encode('utf-8')

    # function to print out status while downloading
    def download_progress_hook(progress):
      status = progress.get('status')
      if status in ('finished', 'error'):
        # we always get an 'error' progress when the video finishes downloading.
        # not sure why. ignore it.
        return
      elif status == 'downloading':
        p = lambda field: progress.get(field) or ''
        msg = '<span><progress max="100" value="%s"></progress> of %s at %s in %s...</span>' % (
          p('_percent_str'), p('_total_bytes_str') or p('_total_bytes_estimate_str'),
          p('_speed_str'), p('_eta_str'))
      else:
        msg = status+ '<br />\n'
      write(msg)

    # fetch video info (resolves URL) to see if we've already downloaded it
    options = {
      # ext4 max filename length is 255 bytes. use format precision to truncate
      # url part of filename if necessary.
      'outtmpl': '/tmp/%(webpage_url).240s',
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
    filename_prefix = ydl.prepare_filename(info)
    options['outtmpl'] = filename_prefix + '.%(ext)s'
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
      yield 'Downloading and extracting audio...<br />\n'
      with handle_errors(write):
        youtube_dl.YoutubeDL(options).download([url])

      # upload to S3
      # http://docs.pythonboto.org/en/latest/s3_tut.html
      yield 'Uploading to S3...<br />\n'

      def upload_callback(sent, total):
        write('<span><progress max="100" value="%s"></progress> </span>\n' % (sent * 100 / total))

      key.set_contents_from_filename(filename, cb=upload_callback)
      key.make_public()
      os.remove(filename)

    # generate description
    description = info.get('description') or ''
    footer = """\
Original video: %s
Downloaded by http://huffduff-video.snarfed.org/""" % url
    if description:
      footer = """

===
""" + footer

    max_len = 1500 - len(footer)
    if len(description) > max_len:
      description = description[:max_len] + '...'
    description += footer

    # open 'Huffduff it' page
    yield """Opening Huffduffer dialog...
<script type="text/javascript">
window.location = "https://huffduffer.com/add?popup=true&%s";
</script>
</body>
</html>""" % urllib.urlencode([(k, v.encode('utf-8')) for k, v in
      (('bookmark[url]', (S3_BASE + s3_key)),
       ('bookmark[title]', info.get('title') or ''),
       ('bookmark[description]', description),
       ('bookmark[tags]', ','.join(info.get('categories') or [])),
     )])

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
    write('</body>\n</html>')
    raise
