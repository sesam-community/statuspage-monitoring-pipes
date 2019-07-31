FROM python:3-alpine

LABEL author="ravish.ranjan@sesam.io"

RUN apk update
RUN apk add tzdata
RUN apk add openssh
RUN rm -f /etc/localtime
RUN ln -s /usr/share/zoneinfo/Europe/Oslo /etc/localtime
RUN pip3 install --upgrade pip

COPY ./service/requirements.txt /service/requirements.txt
RUN pip3 install -r /service/requirements.txt
COPY ./service /service

WORKDIR /service

RUN echo '*/2  *  *  *  *    /service/monitoringpipes.py' > /etc/crontabs/root
CMD crond -l 2 -f

