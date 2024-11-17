# huffduff-video

<b><a href="https://github.com/snarfed/huffduff-video/issues/52#issuecomment-2369160227">huffduff-video has been decommissioned.</a> So long, and thanks for all the fish!

For alternatives, check out <a href="https://breadcrum.net/">Breadcrum</a>, <a href="https://podqueue.fm/">PodQueue</a>, <a href="https://www.podify.org/">Podify</a>, and <a href="https://youtube-dl-api-server.readthedocs.io/">youtube-dl-api-server</a>.</b>

Extracts the audio from videos on YouTube, Vimeo, and [many more sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) and sends it to [Huffduffer](http://huffduffer.com/).

See [huffduff-video.snarfed.org](https://huffduff-video.snarfed.org/) for bookmarklet and usage details.

Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download the video and extract its audio track. Stores the resulting MP3 file in [Backblaze B2](https://www.backblaze.com/b2/).

License: this project is placed in the public domain. Alternatively, you may use it under the [CC0 license](http://creativecommons.org/publicdomain/zero/1.0/).


## Related projects

* [Podify](https://www.podify.org/) is a self-hosted app that also serves feeds of the generated MP3 files. Backed by youtube-dl.
* [youtube-dl-api-server](https://github.com/jaimeMF/youtube-dl-api-server) is a web front-end that uses youtube-dl to extract and return a video's metadata.
* [Flask webapp and Chrome extension](https://charlesleifer.com/blog/a-flask-front-end-and-chrome-extension-for-youtube-dl/) for using youtube-dl to download a video to local disk.
* [iOS workflow](http://www.512pixels.net/blog/2014/12/from-youtube-to-huffduffer-with-workflow) that does the same thing as huffduff-video, except all client side: downloads a YouTube video, converts it to MP3, uploads the MP3 to Dropbox, and passes it to Huffduffer.


## Requirements

huffduff-video has a few specific requirements that make it a bit harder than usual to find a host, so right now it's on a full VM, on AWS EC2. I'd love to switch to a serverless/containerized host instead, but I haven't found one that satisfies all of the requirements yet:

* Python 3 WSGI application server
* able to install and use [ffmpeg](https://ffmpeg.org/), generally as a system package
* long-running HTTP requests, often over 60s
* streaming HTTP responses aka "hanging GETs"
* >= 1G memory
* >= 2G disk (largest output file in Dec 2019 was 1.7G)
* Lots of egress bandwidth, often >200G/mo

Many of the major serverless PaaS hosts didn't/don't support all of these, especially streaming HTTP responses, since they often have a frontend in front of the application server that buffers entire HTTP responses before returning them.

* [AWS Lambda](https://aws.amazon.com/lambda/): [only 512MB disk](https://docs.aws.amazon.com/lambda/latest/dg/running-lambda-code.html) but [can use EFS for more](https://aws.amazon.com/blogs/aws/new-a-shared-file-system-for-your-lambda-functions/); ~[only Java](https://docs.aws.amazon.com/lambda/latest/dg/java-handler-io-type-stream.html)~ [supports streaming](https://aws.amazon.com/blogs/compute/introducing-aws-lambda-response-streaming/), other languages unclear; [expensive-ish egress bandwidth](https://aws.amazon.com/ec2/pricing/on-demand/) ($.09/G)
* [Google Cloud Run](https://cloud.google.com/run/): ~[no streaming](https://cloud.google.com/run/docs/issues#grpc_websocket)~ [now supports streaming!](https://cloud.google.com/blog/products/serverless/cloud-run-now-supports-http-grpc-server-streaming) [In memory file system though](https://cloud.google.com/run/docs/reference/container-contract#filesystem), which gets expensive; [expensive-ish egress bandwidth](https://cloud.google.com/network-tiers/pricing#premium-pricing) ($.085/G)
* [App Engine Standard](https://cloud.google.com/appengine/docs/standard/): [no streaming](https://cloud.google.com/appengine/docs/standard/python3/how-requests-are-handled#streaming_responses) or system packages
* [App Engine Flexible](https://cloud.google.com/appengine/docs/flexible/): pricing is a bit prohibitive, ~$40/mo minimum
* [Azure Functions](https://azure.microsoft.com/en-us/services/functions/) and [App Service](https://azure.microsoft.com/en-us/services/app-service/): [seems like no streaming or system packages](https://docs.microsoft.com/en-us/azure/app-service/overview), but hard to tell for sure

Most other smaller serverless hosts (eg [Heroku](https://www.heroku.com/python), [Zeit](https://zeit.co/now), [Serverless](https://serverless.com/)) don't allow installing system packages like ffmpeg or support streaming HTTP responses either.


## Cost and storage

[I track monthly costs here.](https://docs.google.com/spreadsheets/d/1L578Dvfgi5UJpDM_Gy65Mu8iI0rKAXGB32R0DXuypVc/edit#gid=1172964992) They come from [this B2 billing page](https://secure.backblaze.com/billing.htm), and before that, [this AWS billing page](https://console.aws.amazon.com/billing/home?region=us-west-2#/paymenthistory/history?redirected). The [B2 bucket web UI](https://secure.backblaze.com/b2_buckets.htm) shows the current total number of files and total bytes stored in the `huffduff-video` bucket.

I've configured the [bucket's lifecycle](https://www.backblaze.com/b2/docs/lifecycle_rules.html) to hide files after 31 days, and delete them 1 day after that. I also [configured the bucket settings](https://www.backblaze.com/b2/docs/downloading.html) to send the `Cache-Control: max-age=210240` HTTP header to let clients cache files for up to a year.

I originally used AWS S3 instead of B2, but S3 eventually got too expensive. As of 11/21/2019, huffduff-video was storing ~200GB steady state, and downloads were using well over 2T/month of bandwidth, so my S3 bill alone was >$200/month.


## System setup

Currently on an [AWS EC2 t2.micro instance](https://aws.amazon.com/ec2/instance-types/) on [Ubuntu 20](https://ubuntu.com/server/docs). [`unattended-upgrades` is on](https://wiki.debian.org/UnattendedUpgrades), with the default configuration; logs are in `/var/log/unattended-upgrades/`.

I started it originally on a t2.micro. I migrated it to a t2.nano on 2016-03-24, but usage outgrew the nano's CPU quota, so I migrated back to a t2.micro on 2016-05-25.

I did both migrations by making an snapshot of the t2.micro's EBS volume, making an AMI from the snapshot, then launching a new t2.nano instance using that AMI. [Details.](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-an-ami-ebs.html#creating-launching-ami-from-snapshot)

Here's how I set it up:

```shell
# set up swap
sudo dd if=/dev/zero of=/var/swapfile bs=1M count=4096
sudo chmod 600 /var/swapfile
sudo mkswap /var/swapfile
sudo swapon /var/swapfile

# add my dotfiles
mkdir src
cd src
git clone git@github.com:snarfed/dotfiles.git
cd
ln -s src/dotfiles/.cshrc
ln -s src/dotfiles/.gitconfig
ln -s src/dotfiles/.git_excludes
ln -s src/dotfiles/.python

# install core system packages and config
sudo apt-get update
sudo apt-get install apache2 libapache2-mod-wsgi-py3 tcsh python3 python3-pip ffmpeg
sudo pip3 install -U pip
sudo chsh ubuntu
# enter /bin/tcsh

# install and set up huffduff-video
cd ~/src
git clone https://github.com/snarfed/huffduff-video.git
cd huffduff-video
sudo pip3 install -r requirements.txt

# add these lines to /etc/httpd/conf/httpd.conf
#
# # rest is for huffduff-video!
# Options FollowSymLinks
# WSGIScriptAlias /get /var/www/cgi-bin/app.py
# LogLevel info
#
# # tune number of prefork server processes
# StartServers       8
# ServerLimit        12
# MaxClients         12
# MaxRequestsPerChild  4000

# start apache
sudo service apache2 start
systemctl status apache2.service
sudo systemctl enable apache2.service
sudo chmod a+rx /var/log/apache2
sudo chmod -R a+r /var/log/apache2

# on local laptop
cd ~/src/huffduff-video/
scp b2_* aws_* ubuntu@[IP]:src/huffduff-video/

# back on EC2
cd /var/www/
sudo mkdir cgi-bin
cd cgi-bin
sudo ln -s ~/src/huffduff-video/app.py
cd /var/www/html
sudo ln -s ~/src/huffduff-video/static/index.html
sudo ln -s ~/src/huffduff-video/static/robots.txt
sudo ln -s ~/src/huffduff-video/static/util.js

# install cron jobs
cd
cat > ~/crontab << EOF
# clean up /tmp every hour
0 * * * *  find /tmp/ -user www-data -not -newermt yesterday | xargs rm
# auto upgrade yt-dlp daily
10 10 * * *  sudo pip3 install -U yt-dlp; sudo service apache2 restart
# recopy robots.txt to S3 since our bucket expiration policy deletes it monthly
1 2 3 * *  aws s3 cp --acl=public-read ~/src/huffduff-video/s3_robots.txt s3://huffduff-video/robots.txt
EOF
crontab crontab
```


### Local development

It's possible to set Apache up on macOS to run Python like the production Linux setup, eg with Homebrew Apache and UWSGI, but it's a bit complicated. The simpler approach is to make a virtualenv, install `requirements.txt` and `gunicorn` in it, and then run `appp.py` under `gunicorn` with eg :

```sh
gunicorn --workers 1 --threads 10 -b :8080 app
```

The app will serve on [localhost:8080](http://localhost:8080/). Run with eg http://localhost:8080/?url=...


### Upgrading OS

huffduff-video is pretty small and simple, it doesn't have many unusual dependencies or needs, so I've generally had good luck using Ubuntu's [`do-release-upgrade`](https://askubuntu.com/questions/409555/what-does-do-release-upgrade-really-do) tool to [upgrade from one Ubuntu LTS version to the next](https://ubuntu.com/server/docs/how-to-upgrade-your-release) ([more](https://help.ubuntu.com/community/Upgrades), [even more](https://help.ubuntu.com/community/UpgradeNotes)):

```sh
sudo apt-get update
sudo apt-get upgrade
sudo do-release-upgrade
```

Python installed packages may disappear, make sure to reinstall those with sudo! Otherwise Apache's mod_wsgi won't see them, or will see older versions.

```
sudo pip3 install -r requirements.txt
```


## SSL

I followed the [Certbot Apache instructions](https://certbot.eff.org/instructions?ws=apache&os=ubuntufocal) to mint an SSL certificate, install it, and set up a cron job to renew it every 3 months:

```sh
sudo snap install core; sudo snap refresh core
sudo snap install --classic certbot
sudo certbot --apache
# answer questions; domain is huffduff-video.snarfed.org
```


## Monitoring

I use [Honeycomb](https://www.honeycomb.io/) to monitor huffduff-video with black box HTTP probes to its home page. If enough of them fail in a given time window, it emails me.

I use [CloudWatch](https://console.aws.amazon.com/cloudwatch/) to monitor and alert on EC2 instance system checks and CPU quota. When alarms fire, it emails me.


### System metrics

To get system-level custom metrics for memory, swap, and disk space, set up [Amazon's custom monitoring scripts](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/mon-scripts-perl.html).

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

# WSGI writes Python exception stack traces to this log file across multiple
# lines, and I'd love to collect them multi_line_start_pattern or something
# similar, but each line is prefixed with the same timestamp + severity + etc
# prefix as other lines, so I can't.
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
* define a few [metric filters](https://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/FilterAndPatternSyntax.html)
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


## Understanding bandwidth usage

Back in April 2015, I did a bit of research to understand who was downloading huffduff-video files, to see if I could optimize its bandwidth usage by blocking non-human users.

As always, measure first, then optimize. To learn a bit more about who's downloading these files, I turned on [S3 access logging](http://docs.aws.amazon.com/AmazonS3/latest/dev/ServerLogs.html), waited 24h, then ran these commands to collect and aggregate the logs:

```shell
aws --profile personal s3 sync s3://huffduff-video/logs .
grep -R REST.GET.OBJECT . | grep ' 200 ' | grep -vE 'robots.txt|logs/20' \
  | sed -E 's/[A-Za-z0-9\/+=_-]{32,76}/X/g' | cut -d' ' -f8,20- | sort | uniq -c | sort -n -r > user_agents
grep -R REST.GET.OBJECT . | grep ' 200 ' | grep -vE 'robots.txt|logs/20' \
  | cut -d' ' -f5 | sort | uniq -c | sort -n -r > ips
```

This gave me some useful baseline numbers. Over a 24h period, there were 482 downloads, 318 of which came from bots. (That's 2/3!) Out of the six top user agents by downloads, five were bots. The one exception was the [Overcast](http://overcast.fm/) podcast app.

* [Flipboard](https://flipboard.com/) Proxy (142 downloads)
* [Googlebot](http://www.google.com/bot.html) (67)
* [Twitterbot](https://dev.twitter.com/cards/getting-started#crawling) (39)
* [Overcast](http://overcast.fm/) (47)
* [Yahoo! Slurp](http://help.yahoo.com/help/us/ysearch/slurp) (36)
* [Googlebot-Video](https://support.google.com/webmasters/answer/1061943) (34)

(Side note: Googlebot-Video is polite and includes `Etag` or `If-Modified-Since` when it refetches files. It sent 68 requests, but exactly half of those resulted in an empty `304` response. Thanks Googlebot-Video!)

I switched huffduff-video to use S3 URLs on the `huffduff-video.s3.amazonaws.com` [virtual host](http://docs.aws.amazon.com/AmazonS3/latest/dev/VirtualHosting.html), added a [`robots.txt` file](https://github.com/snarfed/huffduff-video/tree/master/s3_robots.txt) that blocks all bots, waited 24h, and then measured again. The vast majority of huffduff-video links on [Huffduffer](http://huffduffer.com/) are still on the `s3.amazonaws.com` domain, which doesn't serve my `robots.txt`, so I didn't expect a big difference...but I was wrong. Twitterbot had roughly the same number, but the rest were way down:

* [Overcast](http://overcast.fm/) (76)
* [Twitterbot](https://dev.twitter.com/cards/getting-started#crawling) (36)
* [FlipboardProxy](https://flipboard.com/) (33)
* iTunes (OS X) (21)
* [Yahoo! Slurp](http://help.yahoo.com/help/us/ysearch/slurp) (20)
* libwww-perl (18)
* [Googlebot](http://www.google.com/bot.html) (14)

([Googlebot-Video](https://support.google.com/webmasters/answer/1061943) was way farther down the chart with just 4 downloads.)

This may have been due to the fact that my first measurement was Wed-Thurs, and the second was Fri-Sat, which are slower social media and link sharing days. Still, I'm hoping some of it was due to `robots.txt`. Fingers crossed the bots will eventually go away altogether!

To update the `robots.txt` file:

```shell
aws --profile personal s3 cp --acl=public-read ~/src/huffduff-video/s3_robots.txt s3://huffduff-video/robots.txt
```

I put this in a cron job to run every 30d. I had to run `aws configure` first and give it the key id and secret.

To find a specific bot's IPs:

```shell
$ grep -R FlipboardProxy . | cut -d' ' -f5 |sort |uniq
34.207.219.235
34.229.167.12
34.229.216.231
52.201.0.135
52.207.240.171
54.152.58.154
54.210.190.43
54.210.24.16
```

...and then to block them, [add them to the bucket policy](https://docs.aws.amazon.com/AmazonS3/latest/dev/example-bucket-policies.html):

```json
{
  "Version": "2012-10-17",
  "Id": "Block IPs",
  "Statement": [
    {
      "Sid": "Block FlipboardProxy (IPs collected 1/25-26/2017)",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::huffduff-video/*",
      "Condition": {
        "IpAddress": {
          "aws:SourceIp": [
            "34.207.219.235/32",
            "34.229.167.12/32",
            "34.229.216.231/32",
            "52.201.0.135/32",
            "52.207.240.171/32",
            "54.152.58.154/32",
            "54.210.190.43/32",
            "54.210.24.16/32"
          ]
        }
      }
    }
  ]
}
```

While doing this, I discovered something a bit interesting: Huffduffer itself seems to download a copy of every podcast that gets huffduffed, ie the full MP3 file. It does this with no user agent, from 146.185.159.94, which reverse DNS resolves to [huffduffer.com](https://huffduffer.com/).

I can't tell that any Huffduffer feature is based on the actual audio from each podcast, so I wonder why they download them. I doubt they keep them all. [Jeremy probably knows why!](https://adactio.com/)

Something also downloads a lot from 54.154.42.3 (on Amazon EC2) with user agent `Ruby`. No reverse DNS there though.
