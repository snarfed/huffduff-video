"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: http://youtu.be/6dyWlM4ej3Q
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import logging
import os
import re
import urllib

import boto
import webapp2
import youtube_dl


def read(filename):
  with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)) as f:
    return f.read().strip()

AWS_KEY_ID = read('aws_key_id')
AWS_SECRET_KEY = read('aws_secret_key')
S3_BUCKET = 'huffduff-video'
S3_BASE = 'https://s3-us-west-2.amazonaws.com/%s/' % S3_BUCKET


class GetHandler(webapp2.RequestHandler):

  def get(self):
    self.response.headers['Content-Type'] = 'text/html'

    url = self.request.get('url')
    if not url:
      self.abort(400, 'Missing required parameter: url')
    logging.info('URL: %s', url)

    # TODO: stream output. webapp2 evidently doesn't support it. :(
    # https://webapp-improved.appspot.com/guide/response.html
    # maybe webob can natively? WSGI definitely can:
    # http://lucumr.pocoo.org/2011/7/27/the-pluggable-pipedream/#the-wsgi-quirks
    self.response.out.write("""\
<html>
<body>
Fetching %s <br />
""" % url)

    # fetch video info (resolves URL) to see if we've already downloaded it
    ydl = youtube_dl.YoutubeDL({
      'outtmpl': '/tmp/%(webpage_url)s.%(ext)s',
      'restrictfilenames': True,  # don't allow & or spaces in file names
      'logger': logging,
      'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
      }],
      'progress_hooks': [self.progress_hook],
    })
    info = ydl.extract_info(url, download=False)

    # prepare_filename() returns the video filename, not the postprocessed one,
    # so change the extension manually.
    filename = os.path.splitext(ydl.prepare_filename(info))[0] + '.mp3'

    s3 = boto.connect_s3(aws_access_key_id=AWS_KEY_ID,
                         aws_secret_access_key=AWS_SECRET_KEY)
    bucket = s3.get_bucket(S3_BUCKET)
    s3_key = self.generate_s3_key(filename)
    key = bucket.get_key(s3_key, validate=False)

    if key.exists():
      self.response.out.write('Already downloaded! <br />\n')
    else:
      # download video and extract mp3
      self.response.out.write('Downloading to %s <br />\n' % filename)
      ydl.download([url])

      # upload to S3
      # http://docs.pythonboto.org/en/latest/s3_tut.html
      self.response.out.write('Uploading to %s <br />\n' % s3_key)
      key.set_contents_from_filename(filename)
      key.make_public()

    # open 'Huffduff it' page
    description = info.get('description', '')
    if len(description) > 1500:
      description = description[:1500] + '...'

    self.response.out.write("""
<script type="text/javascript">
window.location = "https://huffduffer.com/add?%s";
</script>
</body>
</html>""" % urllib.urlencode({
      'bookmark[url]': S3_BASE + s3_key,
      'bookmark[title]': info.get('title', ''),
      'bookmark[description]': description,
      'bookmark[tags]': ','.join(info.get('categories', [])),
    }))

    # alternative:
    # http://themindfulbit.com/blog/optimizing-your-podcast-site-for-huffduffer

  def progress_hook(self, progress):
    self.response.out.write(' '.join((
      progress.get(field) or '' for field in
      ('status', '_percent_str', '_speed_str ', '_eta_str'))) + '<br />\n')

  def generate_s3_key(self, filename):
    """Generates the S3 key for a given MP3 filename.

    MP3 filenames will look like:
      /tmp/https_-_www.youtube.com_watchv=6dyWlM4ej3Q.mp3

    S3 keys strip the path, scheme, and leading www., mobile, or m.:
      youtube.com_watchv=6dyWlM4ej3Q.mp3
    """
    return re.sub('^https?_-_((www|m|mobile).)?', '', os.path.basename(filename))


application = webapp2.WSGIApplication(
  [('/get', GetHandler),
   ], debug=False)
