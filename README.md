# huffduff-video

Extracts the audio from videos on YouTube, Vimeo, and
[many more sites](http://rg3.github.io/youtube-dl/supportedsites.html)
and sends it to [Huffduffer](http://huffduffer.com/).

See [huffduff-video.snarfed.org](https://huffduff-video.snarfed.org/)
for bookmarklet and usage details.

Uses [youtube-dl](http://rg3.github.io/youtube-dl/) to download the video and
extract its audio track. Stores the resulting MP3 file in
[S3](https://aws.amazon.com/s3).

License: this project is placed in the public domain. Alternatively, you may use
it under the [CC0 license](http://creativecommons.org/publicdomain/zero/1.0/).


## Related projects

* [youtube-dl-api-server](https://github.com/jaimeMF/youtube-dl-api-server) is a
  web front-end that uses youtube-dl to extract and return a video's metadata.
* [Flask webapp and Chrome extension](https://charlesleifer.com/blog/a-flask-front-end-and-chrome-extension-for-youtube-dl/) for using youtube-dl to download a video to local disk.
* [iOS workflow](http://www.512pixels.net/blog/2014/12/from-youtube-to-huffduffer-with-workflow) that does the same thing as huffduff-video, except all client side: downloads a YouTube video, converts it to MP3, uploads the MP3 to Dropbox, and passes it to Huffduffer.


## AWS Setup

Currently on EC2 t2.micro instance. Here's how to setup (but hopefully only for
posterity since I snapshotted an image):

```shell
sudo yum install git httpd-devel mod_wsgi python-devel python26-pip tcsh telnet
sudo yum groupinstall 'Web Server' 'PHP Support'
sudo pip install boto webob youtube-dl

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
