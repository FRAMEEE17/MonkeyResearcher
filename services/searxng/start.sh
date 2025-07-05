#!/bin/bash

# Set UID and GID to current user
export UID=$(id -u)
export GID=$(id -g)

docker compose up -d