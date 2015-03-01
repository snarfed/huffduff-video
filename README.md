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


## Development notes

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
