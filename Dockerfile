# Currently unused. Originally used for Google Cloud Run. Ideally we'd use this
# again at some point on some serverless platform that supports containers and
# streaming HTTP responses!
#
# Uses the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.7-slim

# Install production dependencies.
RUN apt-get update -y && apt-get install -y ffmpeg && apt-get clean
RUN pip install b2sdk webob youtube-dl gunicorn

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers $WORKERS --threads 8 app:application
