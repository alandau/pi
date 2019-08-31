#!/bin/sh

cd ~/youtube-dl
git stash && git pull && git stash pop && echo OK || echo Error
