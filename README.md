# huffduff-video

Extracts the audio from videos on YouTube, Vimeo, and [many more sites](http://rg3.github.io/youtube-dl/supportedsites.html) and sends it to [Huffduffer](http://huffduffer.com/).

See [huffduff-video.snarfed.org](https://huffduff-video.snarfed.org/) for bookmarklet and usage details.

Uses [youtube-dl](http://rg3.github.io/youtube-dl/) to download the video and extract its audio track. Stores the resulting MP3 file in [Backblaze B2](https://www.backblaze.com/b2/).

License: this project is placed in the public domain. Alternatively, you may use it under the [CC0 license](http://creativecommons.org/publicdomain/zero/1.0/).


## Related projects

* [youtube-dl-api-server](https://github.com/jaimeMF/youtube-dl-api-server) is a web front-end that uses youtube-dl to extract and return a video's metadata.
* [Flask webapp and Chrome extension](https://charlesleifer.com/blog/a-flask-front-end-and-chrome-extension-for-youtube-dl/) for using youtube-dl to download a video to local disk.
* [iOS workflow](http://www.512pixels.net/blog/2014/12/from-youtube-to-huffduffer-with-workflow) that does the same thing as huffduff-video, except all client side: downloads a YouTube video, converts it to MP3, uploads the MP3 to Dropbox, and passes it to Huffduffer.


## Development and ops

huffduff-video runs on [Google Cloud Run](https://cloud.google.com/run/), a fully managed [Knative](https://knative.dev/) service. It's a simple Python 3 WSGI application in [app.py](https://github.com/snarfed/huffduff-video/blob/master/app.py), served by [gunicorn](https://docs.gunicorn.org/en/) inside a [Docker container](https://github.com/snarfed/huffduff-video/blob/master/Dockerfile). Generated MP3 files are uploaded to and served from [Backblaze B2](https://www.backblaze.com/b2/).

(Before Cloud Run, [huffduff-video originally ran on AWS EC2](https://github.com/snarfed/huffduff-video/blob/fed4ba636dc0d7936bed2ba4ab6671288e2f1d58/README.md#system-setup).)

To work on it, first fork and clone this repo. Then, in the repo root dir, build and run it locally:

```sh
docker build . --tag gcr.io/huffduff-video/app
setenv PORT 8080 && docker run -p 9090:${PORT} -e PORT=${PORT} gcr.io/huffduff-video/app
```

Once your changes are working and you're ready to deploy, you'll need the [Google Cloud SDK](https://cloud.google.com/sdk/docs/) installed. Then, you can either push the Docker image you built locally with:

```sh
gcloud auth configure-docker  # only needed the first time
gcloud config set project huffduff-video
docker push gcr.io/huffduff-video/app
```

...or rebuild it in [Cloud Build](https://cloud.google.com/cloud-build/):

```sh
gcloud builds submit --tag gcr.io/huffduff-video/app
```

Now, you're ready to deploy!

```sh
gcloud run deploy app --image gcr.io/huffduff-video/app --region=us-central1 --platform managed --memory=2Gi --concurrency=4
```

### Static site

The static files at [huffduff-video.snarfed.org](https://huffduff-video.snarfed.org/) are served by [Firebase Hosting](https://firebase.google.com/docs/hosting/). I [followed these instructions to set it up](https://firebase.google.com/docs/hosting/quickstart), added a [rewrites]() section to `[firebase.json](https://github.com/snarfed/huffduff-video/blob/master/firebase.json)` to [redirect `/get` to my Cloud Run container](https://firebase.google.com/docs/hosting/cloud-run#direct_requests_to_container), and then deployed.

```sh
yarn global add firebase-tools
firebase login
firebase init  # choose Hosting, use directory static/, don't overwrite static/index.html
firebase deploy
```

I then saw the site serving on [huffduff-video.firebaseapp.com](https://huffduff-video.firebaseapp.com/), and I could [manage it in the Firebase console](https://console.firebase.google.com/u/0/project/huffduff-video/hosting/main). All I had to do then was [connect the huffduff-video.snarfed.org subdomain](https://firebase.google.com/docs/hosting/custom-domain), and I was all set.


## Cost and storage

[I track monthly costs here.](https://docs.google.com/spreadsheets/d/1L578Dvfgi5UJpDM_Gy65Mu8iI0rKAXGB32R0DXuypVc/edit#gid=1172964992) They come from these [B2 billing](https://secure.backblaze.com/billing.htm) and [Google Cloud billing](https://console.cloud.google.com/billing/00904A-705F88-DAEEDC/reports) pages, and before that, [this AWS billing page](https://console.aws.amazon.com/billing/home?region=us-west-2#/paymenthistory/history?redirected). The [B2 bucket web UI](https://secure.backblaze.com/b2_buckets.htm) shows the current total number of files and total bytes stored in the `huffduff-video` bucket.

I've configured the [bucket's lifecycle](https://www.backblaze.com/b2/docs/lifecycle_rules.html) to hide files after 31 days, and delete them 1 day after that. I also [configured the bucket settings](https://www.backblaze.com/b2/docs/downloading.html) to send the `Cache-Control: max-age=210240` HTTP header to let clients cache files for up to a year.

I originally used AWS S3 instead of B2, but S3 eventually got too expensive. As of 11/21/2019, huffduff-video was storing ~200GB steady state, and downloads were using well over 2T/month of bandwidth, so my S3 bill alone was >$200/month.


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
