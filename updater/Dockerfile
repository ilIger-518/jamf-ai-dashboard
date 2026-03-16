FROM docker:26-cli

# Python + pip + git (docker:26-cli is Alpine-based)
RUN apk add --no-cache python3 py3-pip git bash

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY updater.py .

EXPOSE 8089

CMD ["python3", "updater.py"]
