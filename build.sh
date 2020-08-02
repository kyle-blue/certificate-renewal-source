#!/bin/bash

REGISTRY="registry.gitlab.com/bit-memo/deprecated/bitmemo-old-monorepo"
NAME="cert-renewal"
DIR=$(dirname "$0")
cd "$DIR"
docker build . -t "$REGISTRY/$NAME:1.1" -t "$REGISTRY/$NAME:latest" 
docker push "$REGISTRY/$NAME" # Pushes for every tag