# huffduff-video
Extract the audio from Youtube videos (and many others!) and send it to
[Huffduffer](http://huffduffer.com/).

Deployed at [huffduff-video.appspot.com](https://huffduff-video.appspot.com/).
To use, drag [this bookmarklet]() (TODO!) to your browser's bookmark menu or
toolbar, then just click it whenever you're on a video that you'd like to
huffduff.

Uses [youtube-dl](http://rg3.github.io/youtube-dl/) to download the video and
extract its audio track, writes the resulting MP3 file to
[Google Cloud Storage](https://cloud.google.com/storage/), and sends it to
Huffduffer.

Supports all video sites that youtube-dl supports.

License: this project is placed in the public domain. Alternatively, you may use
it under the [CC0 license](http://creativecommons.org/publicdomain/zero/1.0/).


## Related projects
* [youtube-dl-api-server](https://github.com/jaimeMF/youtube-dl-api-server) is a
  web front-end that uses youtube-dl to extract and return a video's metadata.
* [Flask webapp and Chrome extension](https://charlesleifer.com/blog/a-flask-front-end-and-chrome-extension-for-youtube-dl/) for using youtube-dl to download a video to local disk.
* [iOS workflow](http://www.512pixels.net/blog/2014/12/from-youtube-to-huffduffer-with-workflow) that does the same thing as huffduff-video, except all client side: downloads a YouTube video, converts it to MP3, uploads the MP3 to Dropbox, and passes it to Huffduffer.


## Development notes

CURRENT PROBLEM: extracting audio uses command line ffmpeg or avconv, which
won't work on app engine. maybe switch to full VPS?

digital ocean, EC2, google compute engine all charge ~$.01/hr for smallest
instance, which is 1 (abstract) core + .5-1GB ram. amazon is free for 1y.

http://aws.amazon.com/ec2/pricing/
http://aws.amazon.com/free/
https://cloud.google.com/compute/?hl=en_US#pricing
https://www.digitalocean.com/pricing/

AWS lambda (PaaS) would be nice but only supports Node.js right now. can run
arbitary binaries if they come as node packages - they even mention node-ffmpeg
as an example, and there's even a node youtube-dl package!
http://aws.amazon.com/lambda/getting-started/
http://aws.amazon.com/lambda/faqs/
https://github.com/fent/node-youtube-dl

using youtube-dl as library
https://github.com/rg3/youtube-dl/blob/master/README.md#developer-instructions
https://github.com/rg3/youtube-dl/issues/1129

streaming upload to google cloud storage with boto library
takes stream object (e.g. file handle) as input, reads data from it, uploads
https://cloud.google.com/storage/docs/concepts-techniques#streaming

boto library
http://docs.pythonboto.org/en/latest/
https://github.com/boto/boto

even better, app engine GCS api expose a file object interface!
https://cloud.google.com/appengine/docs/python/googlecloudstorageclient/functions#open

similar project, embeds youtube-dl in app engine but only to get video metadata
https://github.com/jaimeMF/youtube-dl-api-server

## AWS Setup

Currently on EC2 t2.micro instance. Here's how to setup (but hopefully only for
posterity since I snapshotted an image):

```shell
sudo yum install git httpd-devel mod_wsgi python-devel python26-pip tcsh telnet
sudo yum groupinstall 'Web Server' 'PHP Support'
sudo pip install boto webapp2 webob youtube-dl

# Amazon Linux AMI has mod_wsgi 3.2, but we need 3.4 to prevent this error when
# running youtube-dl under WSGI:
# AttributeError: 'mod_wsgi.Log' object has no attribute 'isatty'
curl -o mod_wsgi-3.4.tar.gz https://modwsgi.googlecode.com/files/mod_wsgi-3.4.tar.gz
tar xvzf mod_wsgi-3.4.tar.gz
cd mod_wsgi-3.4
sudo yum install httpd-devel -y
./configure
sudo make install

# add these lines to /etc/httpd/conf/httpd.conf
#
# # for huffduff-video
# LoadModule wsgi_module /usr/lib64/httpd/modules/mod_wsgi.so
# Options FollowSymLinks
# WSGIScriptAlias /get /var/www/cgi-bin/app.py

# start apache
sudo service httpd start
sudo chkconfig httpd on

# install ffmpeg
wget http://johnvansickle.com/ffmpeg/releases/ffmpeg-release-64bit-static.tar.xz
cd /usr/local/bin
sudo tar xJf ~/ffmpeg-release-64bit-static.tar.xz
cd /usr/bin
sudo ln -s ffmpeg-2.5.4-64bit-static/ffmpeg
sudo ln -s ffmpeg-2.5.4-64bit-static/ffprobe

# clone huffduff-video repo and install for apache
cd ~
mkdir src
chmod a+rx ~/src
cd src
git clone git@github.com:snarfed/huffduff-video.git
# create and fill in aws_key_id and aws_secret_key files

cd /var/www/cgi-bin
sudo ln -s ~/src/huffduff-video/app.py
cd /var/www/html
sudo ln -s ~/src/huffduff-video/static/index.html
```
