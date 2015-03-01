"""Extracts audio from Youtube (etc) videos to send to Huffduffer.
"""

__author__ = ['Ryan Barrett <huffduff-video@ryanb.org>']

import datetime
import logging
import json
import urllib2

from google.appengine.api import app_identity
from google.appengine.ext import cloudstorage
from google.appengine.ext import ndb
import webapp2


class Video(ndb.Model):
  """Key id is video URL."""
  file = ndb.StringProperty()  # GCS full path
  created = ndb.DateTimeProperty(auto_now_add=True)
  updated = ndb.DateTimeProperty(auto_now=True)


class GetHandler(webapp2.RequestHandler):

  def get(self):
    url = util.get_required_param('url')
    logging.info('URL: %s', url)


application = webapp2.WSGIApplication(
  [('/get', GetHandler),
   ], debug=False)
