# Currently unused. Originally used for Google Cloud Run. Ideally we'd use this
# again at some point on some serverless platform that supports containers and
# streaming HTTP responses!
#
# Uses the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.10-slim

# Install production dependencies: ffmpeg & gunicorn
RUN apt-get update -y && apt-get install -y ffmpeg && apt-get clean
RUN pip install --upgrade pip
RUN pip install gunicorn

ENV APP_HOME /app
WORKDIR $APP_HOME

# Install production dependencies.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy local code to the container image.
COPY . ./

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:application
