"""Extracts audio from Youtube (etc) videos to send to Huffduffer.

Short test video: https://www.youtube.com/watch?v=bPHDKygWMWo
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import logging
import json
import urllib2
import sys

import webapp2
import youtube_dl


class GetHandler(webapp2.RequestHandler):

  def get(self):
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
      'logger': logging,
      'progress_hooks': [self.progress_hook],
      })
    # ydl._screen_file = cloudstorage.open(GCS_FILE_TEMPLATE % url, 'w')
    ydl.download([url])

    self.response.out.write('Downloaded to %s', ydl._screen_file.name)

  def progress_hook(self, progress):
    logging.info(`progress`)


application = webapp2.WSGIApplication(
  [('/get', GetHandler),
   ], debug=False)
