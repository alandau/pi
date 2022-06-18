#!/bin/sh

cd ~/yt-dlp
git stash && git pull && git stash pop && echo OK || echo Error
