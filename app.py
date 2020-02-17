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
import urllib.parse

from b2sdk.account_info.in_memory import InMemoryAccountInfo
from b2sdk.api import B2Api
from b2sdk.progress import AbstractProgressListener
import requests
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

B2_KEY_ID = read('b2_key_id')
B2_APP_KEY = read('b2_app_key')
B2_BUCKET = 'huffduff-video'
B2_BASE = 'https://f000.backblazeb2.com/file/%s/' % B2_BUCKET

DOMAIN_BLACKLIST = frozenset((
  'www.bbc.co.uk',  # copyright request on 8/6/2018
  'www.bbc.com',
))

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

  parsed = urllib.parse.urlparse(url)
  if parsed.netloc in DOMAIN_BLACKLIST:
    return webob.exc.HTTPBadRequest(
      'Sorry, this content is not currently supported due to copyright.')(
        environ, start_response)

  write_fn = start_response('200 OK', headers)
  def write(line):
    write_fn(line.encode())

  def run():
    """Generator that does all the work and yields the response body lines.

    TODO: figure out how to catch and log stack traces when this function raises
    an exception. Currently the log only gets the exception message. Wrapping
    the call at the bottom in try/except doesn't work since it's a generator. :/
    """
    yield HTML_HEADER.encode()
    yield ('<div id="progress">\nFetching %s ...<br />' % url).encode()

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
        try:
          percent = float(p('_percent_str').strip('%') or '0')
        except ValueError:
          percent = 0
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
    filename_prefix = ydl.prepare_filename(info)[:245 - len(B2_BASE)]
    options['outtmpl'] = filename_prefix.replace('%', '%%') + '.%(ext)s'
    filename = filename_prefix + '.mp3'

    b2api = B2Api(InMemoryAccountInfo())
    b2api.authorize_account('production', B2_KEY_ID, B2_APP_KEY)
    bucket = b2api.get_bucket_by_name(B2_BUCKET)

    # strip the filename's path, scheme, and leading www., mobile, or m.
    # the resulting filename will look like 'youtube.com_watchv=6dyWlM4ej3Q.mp3'
    b2_filename = re.sub('^https?_-_((www|m|mobile|player).)?', '', os.path.basename(filename))
    b2_url = bucket.get_download_url(b2_filename)

    uploaded_time = datetime.datetime.now()
    existing = requests.head(b2_url)
    if existing.ok:
      yield 'Already downloaded! <br />\n'.encode()
      try:
        uploaded_time = datetime.datetime.utcfromtimestamp(
          int(existing.headers.get('X-Bz-Upload-Timestamp')) / 1000)  # ms
      except:
        # missing or bad header
        pass
    else:
      # download video and extract mp3
      yield 'Downloading (this can take a while)...<br />\n'.encode()
      with handle_errors(write):
        youtube_dl.YoutubeDL(options).download([url])

      # upload to B2
      yield 'Uploading to B2...<br />\n'.encode()

      class WriteProgress(AbstractProgressListener):
        def set_total_bytes(self, total):
          self.total = total

        def bytes_completed(self, sent):
          write('<span><progress max="100" value="%s"></progress><br /> '
                '%.2fMB of %.2fMB</span>\n' % (
                  (sent * 100 / self.total), float(sent) / 1000000,
                  float(self.total) / 1000000))

        def close(self):
          pass

      with WriteProgress() as listener:
        bucket.upload_local_file(filename, b2_filename, progress_listener=listener)
      os.remove(filename)

    # generate description
    description = info.get('description') or ''
    footer = """\
Original video: %s
Downloaded by http://huffduff-video.snarfed.org/ on %s
Available for 30 days after download""" % (
  url, uploaded_time.replace(microsecond=0).ctime())
    if description:
      footer = """

===
""" + footer

    max_len = 1500 - len(footer)
    if len(description) > max_len:
      description = description[:max_len] + '...'
    description += footer

    # open 'Huffduff it' page
    yield ("""\n<br />Opening Huffduffer dialog...
<script type="text/javascript">
window.location = "https://huffduffer.com/add?popup=true&%s";
</script>
""" % urllib.parse.urlencode([(k, v.encode()) for k, v in
      (('bookmark[url]', (b2_url)),
       ('bookmark[title]', info.get('title') or ''),
       ('bookmark[description]', description),
       ('bookmark[tags]', ','.join(info.get('categories') or [])),
     )])).encode()
    yield HTML_FOOTER.encode()

    # alternative:
    # http://themindfulbit.com/blog/optimizing-your-podcast-site-for-huffduffer

  return run()


@contextlib.contextmanager
def handle_errors(write):
  """Wraps youtube_dl calls in a try/except and handles errors."""
  try:
    yield
  except Exception as e:
    write('<p>%s</p>\n' % e)
    if isinstance(e, (youtube_dl.DownloadError, youtube_dl.utils.ExtractorError)):
      write("""\
Here are the <a href="http://rg3.github.io/youtube-dl/supportedsites.html">
supported sites</a>. If this site isn't supported, it may also post
its videos on YouTube. Try there!
""")
    write(HTML_FOOTER)
    raise
