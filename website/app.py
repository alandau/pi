#!/usr/bin/env python

from flask import Flask, render_template, request, redirect, url_for
import subprocess

app = Flask(__name__)

@app.route("/")
def main():
    url = request.args.get('url', '')
    if url == 'about:blank':
        url = ''
    done = request.args.get('done', None)
    direct_url = request.args.get('direct_url', None)
    return render_template('index.html', url=url, base=request.base_url, done=done, direct_url=direct_url)

@app.route("/action")
def action():
    url = request.args.get('url', '')
    direct_url = None
    done = True
    if request.args.get('open', ''):
        subprocess.Popen("DISPLAY=:0 /home/pi/player/player.py '%s'" % url, shell=True)
    elif request.args.get('browser', ''):
        subprocess.Popen("DISPLAY=:0 xdg-open '%s'" % url, shell=True)
    elif request.args.get('yt', ''):
        try:
            direct_url = subprocess.check_output('youtube-dl -f "best[height<=?720][ext=mp4]" -g --no-playlist -- "%s" 2>&1' % url, shell=True).strip()
        except subprocess.CalledProcessError as e:
            done = False
    return redirect(url_for('main', url=url, done=done, direct_url=direct_url))

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
