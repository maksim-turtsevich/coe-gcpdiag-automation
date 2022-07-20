# start by pulling the python image
FROM python:3.10-slim-bullseye

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install -r requirements.txt &&\
    apt-get update &&\
    apt-get install -y curl &&\
    curl -fsSL https://get.docker.com -o get-docker.sh && chmod +x ./get-docker.sh &&\
    ./get-docker.sh

# copy every content from the local file to the image
COPY . /app
RUN ls -l

# Checking vars
#RUN id -u &&\
#    id -n -u &&\
#    id -n -g
#RUN curl https://gcpdiag.dev/gcpdiag.sh >gcpdiag &&\
#    chmod +x gcpdiag &&\
#    ./gcpdiag

#RUN ./gcpdiag
# Handling script issues
#RUN sed -i 's/\r$//' ./gcpdiag


# Install gcpdiag
#RUN ./gcpdiag

# configure the container to run in an executed manner

EXPOSE 5000

ENTRYPOINT [ "python" ]
CMD ["function.py" ]