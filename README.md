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


## Storage

The [`aws` command line tool](https://aws.amazon.com/cli/) is nice, but the man
page isn't very useful.
[Here's the online reference](http://docs.aws.amazon.com/cli/latest/reference/),
[here's `aws s3`](http://docs.aws.amazon.com/cli/latest/reference/s3/index.html)
(high level but minimal), and
[here's `aws s3api`](http://docs.aws.amazon.com/cli/latest/reference/s3api/index.html)
(much more powerful).

Run this see the current usage (from http://serverfault.com/a/644795/274369):

```shell
aws s3api list-objects --bucket huffduff-video \
  --query "[sum(Contents[].Size), length(Contents[])]"
```

Our S3 bucket lifecycle is in
[`s3_lifecycle.json`](/snarfed/huffduff-video/blob/master/s3_lifecycle.json).
I ran these commands to set a lifecycle that deletes files after 90d.
([Config docs](https://docs.aws.amazon.com/AmazonS3/latest/API/RESTBucketPUTlifecycle.html),
[`put-bucket-lifecycle` docs](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-bucket-lifecycle.html).)

```shell
# show an example lifecycle template
aws s3api put-bucket-lifecycle --generate-cli-skeleton

# set the lifecycle
aws s3api put-bucket-lifecycle --bucket huffduff-video \
  --lifecycle-configuration "`json_pp -json_opt loose <s3_lifecycle.json`"

# check that it's there
aws s3api get-bucket-lifecycle --bucket huffduff-video
```


As of 3/10/2015, users are putting roughly 2GB/day into S3, ie 180GB steady
state for the lifecycle period of 90d.
[At $.03/GB/month](https://aws.amazon.com/s3/pricing/#Storage_Pricing), that
costs $5.40/month. I could use
[RRS (Reduced Redundancy Storage)](https://aws.amazon.com/s3/faqs/#Reduced_Redundancy_Storage_%28RRS%29),
which costs [$.024/GB/month](https://aws.amazon.com/s3/pricing/#Storage_Pricing)
ie $4.32/month, but that's not a big difference.


## Monitoring

I set up [CloudWatch](https://console.aws.amazon.com/cloudwatch/) to monitor and
alarm on EC2 instance system checks, billing thresholds, HTTP logs, and
application level exceptions. When alarms fire, it emails and SMSes me.

The
[monitoring alarms](https://console.aws.amazon.com/cloudwatch/home?region=us-west-2)
are in us-west-2 (Oregon), but
the [billing alarms](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1)
have to be in us-east-1 (Virginia). Each region has its own SNS topic for
notifications:
[us-east-1](https://console.aws.amazon.com/sns/v2/home?region=us-east-1#/topics/arn:aws:sns:us-east-1:996569606388:NotifyMe)
[us-west-2](https://console.aws.amazon.com/sns/v2/home?region=us-west-2#/topics/arn:aws:sns:us-west-2:996569606388:huffduff-video)


### System metrics

To get system-level custom metrics for memory, swap, and disk space, I set up
[Amazon's custom monitoring scripts](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/mon-scripts-perl.html).

```shell
sudo yum install perl-DateTime perl-Sys-Syslog perl-LWP-Protocol-https
wget http://aws-cloudwatch.s3.amazonaws.com/downloads/CloudWatchMonitoringScripts-1.2.1.zip
unzip CloudWatchMonitoringScripts-1.2.1.zip
rm CloudWatchMonitoringScripts-1.2.1.zip
cd aws-scripts-mon

cp awscreds.template awscreds.conf
# fill in awscreds.conf
./mon-put-instance-data.pl --aws-credential-file ~/aws-scripts-mon/awscreds.conf --mem-util --swap-util --disk-space-util --disk-path=/ --verify

crontab -e
# add this line:
# * * * * *	./mon-put-instance-data.pl --aws-credential-file ~/aws-scripts-mon/awscreds.conf --mem-util --swap-util --disk-space-util --disk-path=/ --from-cron
```


### Log collection

To set up HTTP and application level monitoring, I had to:
* [add an IAM policy](https://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/QuickStartEC2Instance.html#d0e9135)
* [install the logs agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/QuickStartEC2Instance.html#d0e9218) with `sudo yum install awslogs`
* add my IAM credentials to `/etc/awslogs/awscli.conf` and set region to us-west-2
* add these lines to `/etc/awslogs/awslogs.conf`:
```ini
[/var/log/httpd/access_log]
file = /var/log/httpd/access_log*
log_group_name = /var/log/httpd/access_log
log_stream_name = {instance_id}
datetime_format = %d/%b/%Y:%H:%M:%S %z

[/var/log/httpd/error_log]
file = /var/log/httpd/error_log*
log_group_name = /var/log/httpd/error_log
log_stream_name = {instance_id}
datetime_format = %b %d %H:%M:%S %Y
```
* start the agent and restart it on boot:
```shell
sudo service awslogs start
sudo service awslogs status
sudo chkconfig awslogs on
```
* wait a while, then check that the logs are flowing:
```shell
aws --region us-west-2 logs describe-log-groups
aws --region us-west-2 logs describe-log-streams --log-group-name /var/log/httpd/access_log
aws --region us-west-2 logs describe-log-streams --log-group-name /var/log/httpd/error_log
```
* define a few
[metric filters](https://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/FilterAndPatternSyntax.html)
so we can graph and query HTTP status codes, error messages, etc:
```shell
aws logs put-metric-filter --region us-west-2 \
  --log-group-name /var/log/httpd/access_log \
  --filter-name HTTPRequests \
  --filter-pattern '[ip, id, user, timestamp, request, status, bytes]' \
  --metric-transformations metricName=count,metricNamespace=huffduff-video,metricValue=1

aws logs put-metric-filter --region us-west-2 \
  --log-group-name /var/log/httpd/error_log \
  --filter-name PythonErrors \
  --filter-pattern '[timestamp, error_label, prefix = "ERROR:root:ERROR:", ...]' \
  --metric-transformations metricName=errors,metricNamespace=huffduff-video,metricValue=1

aws --region us-west-2 logs describe-metric-filters --log-group-name /var/log/httpd/access_log
aws --region us-west-2 logs describe-metric-filters --log-group-name /var/log/httpd/error_log
```


## System setup

Currently on EC2 t2.micro instance. Here's how to set it up (hopefully only for
posterity since I snapshotted an image):

```shell
sudo yum install git httpd-devel mod_wsgi python-devel python27-pip tcsh telnet
sudo update-alternatives --set python /usr/bin/python2.7
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
# LogLevel info

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
