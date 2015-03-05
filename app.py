"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: http://youtu.be/6dyWlM4ej3Q
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import logging
import os
import re

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
    self.response.headers['Content-Type'] = 'text/plain'

    url = self.request.get('url')
    if not url:
      self.abort(400, 'Missing required parameter: url')
    logging.info('URL: %s', url)

    ydl = youtube_dl.YoutubeDL({
      'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
      }],
      'restrictfilenames': True,  # don't allow & or spaces in file names
      # 'download_archive': '/var/www/download_archive',
      'outtmpl': '/tmp/%(webpage_url)s.%(ext)s',
      'logger': logging,
      'progress_hooks': [self.progress_hook],
      })

    self.filename = None
    ydl.download([url])

    if not self.filename:
      self.abort(500, 'Failed!')

    self.response.out.write('Downloaded to %s\n' % self.filename)
    s3_key = self.generate_s3_key()
    self.response.out.write('Uploading to %s\n' % s3_key)

    # http://docs.pythonboto.org/en/latest/s3_tut.html
    # TODO: enable static web site hosting? on https://console.aws.amazon.com/s3/home
    s3 = boto.connect_s3(aws_access_key_id=AWS_KEY_ID,
                         aws_secret_access_key=AWS_SECRET_KEY)
    bucket = s3.get_bucket(S3_BUCKET)
    key = bucket.get_key(s3_key, validate=False)
    if not key.exists():
      key.set_contents_from_filename(self.filename)
      key.make_public()

    self.response.out.write('Done!\n')
    # TODO: pop up 'huffduff it' bookmarklet page

  def progress_hook(self, progress):
    self.response.out.write(' '.join((
      progress.get(field) or '' for field in
      ('status', '_percent_str', '_speed_str ', '_eta_str'))))
    self.response.out.write('\n')

    if progress.get('status') == 'finished':
      # progress reports the video filename, not the postprocessed filename, so
      # we have to change the extension manually.
      self.filename = os.path.splitext(progress.get('filename'))[0] + '.mp3'

  def generate_s3_key(self):
    """Generates the S3 key for the MP3 file for a given video URL.

    MP3 files will have filenames that look like:
      /tmp/https_-_www.youtube.com_watchv=6dyWlM4ej3Q.mp3

    S3 keys strip the path, scheme, and leading www., mobile, or m.:
      youtube.com_watchv=6dyWlM4ej3Q.mp3
    """
    return re.sub('^https?_-_((www|m|mobile).)?', '',
                  os.path.splitext(os.path.basename(self.filename)))


application = webapp2.WSGIApplication(
  [('/get', GetHandler),
   ], debug=False)
