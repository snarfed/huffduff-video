"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: http://youtu.be/6dyWlM4ej3Q
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import logging
import os
import re
import urllib

import boto
import webob
import youtube_dl


def read(filename):
  with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)) as f:
    return f.read().strip()

AWS_KEY_ID = read('aws_key_id')
AWS_SECRET_KEY = read('aws_secret_key')
S3_BUCKET = 'huffduff-video'
S3_BASE = 'https://s3-us-west-2.amazonaws.com/%s/' % S3_BUCKET


def application(environ, start_response):
  """Hand-rolled WSGI application so I can stream output.

  ...by returning a generator that yields the response body lines.
  """
  request = webob.Request(environ)
  headers = [('Content-Type', 'text/html')]

  # validate request
  if request.method not in ('GET', 'POST'):
    start_response('405 Method must be GET or POST', headers)
    return

  url = request.params.get('url')
  if not url:
    start_response('400 Missing required parameter: url', headers)
    return

  write = start_response('200 OK', headers)  # the write fn is used in progress_hook

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
<script type="text/javascript">
window.setInterval(function() { window.scrollTo(0, document.body.scrollHeight); }, 500);
</script>
<body>
<h1>huffduff-video</h1>
Fetching %s...<br />""" % (url, url)).encode('utf-8')

    # function to print out status while downloading
    def progress_hook(progress):
      status = progress.get('status')
      if status == 'error':
        # we always get an 'error' progress when the video finishes downloading.
        # not sure why. ignore it.
        return
      elif status == 'downloading':
        p = lambda field: progress.get(field) or ''
        msg = '%s of %s at %s in %s...' % (
          p('_percent_str'), p('_total_bytes_str') or p('_total_bytes_estimate_str'),
          p('_speed_str'), p('_eta_str'))
      else:
        msg = status
      write((msg + '<br />\n').encode('utf-8'))

    # fetch video info (resolves URL) to see if we've already downloaded it
    ydl = youtube_dl.YoutubeDL({
      'outtmpl': '/tmp/%(webpage_url)s.%(ext)s',
      'restrictfilenames': True,  # don't allow & or spaces in file names
      'logger': logging,
      'logtostderr': True,
      'format': 'bestaudio/best',
      'noplaylist': True,
      'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
      }],
      'progress_hooks': [progress_hook],
    })
    info = ydl.extract_info(url, download=False)

    # prepare_filename() returns the video filename, not the postprocessed one,
    # so change the extension manually. the resulting filename will look like:
    #   '/tmp/https_-_www.youtube.com_watchv=6dyWlM4ej3Q.mp3'
    filename = os.path.splitext(ydl.prepare_filename(info))[0] + '.mp3'

    s3 = boto.connect_s3(aws_access_key_id=AWS_KEY_ID,
                         aws_secret_access_key=AWS_SECRET_KEY)
    bucket = s3.get_bucket(S3_BUCKET)
    # strip the filename's path, scheme, and leading www., mobile, or m.
    # the resulting S3 key will look like 'youtube.com_watchv=6dyWlM4ej3Q.mp3'
    s3_key = re.sub('^https?_-_((www|m|mobile).)?', '', os.path.basename(filename))
    key = bucket.get_key(s3_key, validate=False)

    if key.exists():
      yield 'Already downloaded! <br />'
    else:
      # download video and extract mp3
      yield ('Downloading to %s...<br />' % filename).encode('utf-8')
      ydl.download([url])

      # upload to S3
      # http://docs.pythonboto.org/en/latest/s3_tut.html
      yield ('Uploading %s...<br />' % s3_key).encode('utf-8')
      key.set_contents_from_filename(filename)
      key.make_public()

    # open 'Huffduff it' page
    description = info.get('description', '')
    if len(description) > 1500:
      description = description[:1500] + '...'

    yield """\
<script type="text/javascript">
window.location = "https://huffduffer.com/add?popup=true&%s";
</script>
</body>
</html>""" % urllib.urlencode([(k, v.encode('utf-8')) for k, v in
      (('bookmark[url]', (S3_BASE + s3_key)),
       ('bookmark[title]', info.get('title', '')),
       ('bookmark[description]', description),
       ('bookmark[tags]', ','.join(info.get('categories', []))),
     )])

    # alternative:
    # http://themindfulbit.com/blog/optimizing-your-podcast-site-for-huffduffer

  return run()
