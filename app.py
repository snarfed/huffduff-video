"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: https://www.youtube.com/watch?v=bPHDKygWMWo
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import __builtin__
import datetime
import logging
import json
import os
import urllib2
import sys

from google.appengine.ext import ndb
import cloudstorage
import webapp2

# youtube-dl imports these but app engine blocks them and we don't need them, so
# alias them to an arbitrary existing module.
for unused_module in 'fcntl', 'ctypes', 'netrc':
  sys.modules[unused_module] = logging

import youtube_dl

# monkey patches to make youtube-dl work on app engine
sys.stderr.isatty = lambda: False
youtube_dl.extractor.youtube.get_cachedir = lambda *args, **kargs: None
youtube_dl.utils.get_exe_version = \
  youtube_dl.postprocessor.ffmpeg.get_exe_version = lambda *args, **kargs: False

os.rename = lambda src, dst: logging.warning('Not renaming %s to %s', src, dst)

GCS_FILE_TEMPLATE = '/huffduff-video.appspot.com/%s'


class Video(ndb.Model):
  """Key id is video URL."""
  file = ndb.StringProperty()  # GCS full path
  created = ndb.DateTimeProperty(auto_now_add=True)
  updated = ndb.DateTimeProperty(auto_now=True)


class GetHandler(webapp2.RequestHandler):

  def get(self):
    url = self.request.get('url')
    if not url:
      self.abort(400, 'Missing required parameter: %s' % name)
    logging.info('URL: %s', url)

    ydl = youtube_dl.YoutubeDL({
      # 'postprocessors': [{
      #   'key': 'FFmpegExtractAudio',
      #   'preferredcodec': 'mp3',
      #   'preferredquality': '192',
      # }],
      'logger': logging,
      'progress_hooks': [self.progress_hook],
      })
    ydl._screen_file = cloudstorage.open(GCS_FILE_TEMPLATE % url, 'w')

    open_files = []
    orig_open = __builtin__.open
    try:
      def gcs_open(*args, **kwargs):
        # drop everything in mode after r or w
        if len(args) > 1 and args[1]:
          args = list(args)
          mode = args[1] = args[1][:1]
        elif kwargs.get('mode'):
          mode = kwargs['mode'] = kwargs['mode'][:1]
        filename = GCS_FILE_TEMPLATE % args[0]
        file = cloudstorage.open(filename, *args[1:], **kwargs)
        open_files.append(file)
        logging.info('@ Opened %s as %s', filename, mode)
        return file

      __builtin__.open = gcs_open
      ydl.download([url])
    finally:
      __builtin__.open = orig_open
      for file in open_files:
        logging.info('@ Closing %r %s', file, file.__dict__)
        file.close()

    self.response.out.write('Downloading now!')

  def progress_hook(self, progress):
    logging.info(`progress`)


application = webapp2.WSGIApplication(
  [('/get', GetHandler),
   ], debug=False)
