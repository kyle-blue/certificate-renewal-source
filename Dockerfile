FROM python:3.7.7

LABEL maintainer="kyle.blue.nuttall@gmail.com"

COPY ./create_secrets /create_secrets
COPY ./entrypoint.sh /entrypoint.sh

RUN apt -y update && \
    apt -y upgrade && \
    apt -y install certbot

RUN /bin/bash -c "source /create_secrets/venv/bin/activate; pip3 install -r /create_secrets/requirements.txt"

CMD ["/entrypoint.sh"]