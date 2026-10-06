# nginx

[Docs home](README.md) · [Architecture](structure.md) · [Development](development.md) · [Deployment](deployment.md) · [nginx](nginx.md) · [Operations](operations.md) · [Data analysis](data-analysis.md) · [Project README](../README.md)

- [Configuration](#configuration)
- [Changes from DTU's configuration](#changes-from-dtus-configuration)
- [Applying changes](#applying-changes)

## Configuration

nginx was set up by DTU before this project, in `/etc/nginx/conf.d/psqdb.conf`, together
with the certificate (`/etc/nginx/conf.d/ssl-compute.dtu.dk.conf`). It is not part of this
repository and the scripts never touch it. This is the version it should contain:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name psqdb.compute.dtu.dk;
    return 301 https://$host$request_uri;
}

server {
    listen       443 ssl;
    listen       [::]:443 ssl;
    http2        on;
    server_name  psqdb.compute.dtu.dk;
    root         /usr/share/nginx/html;

    include /etc/nginx/conf.d/ssl-compute.dtu.dk.conf;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:2810;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    error_page 404 /404.html;
    location = /40x.html {
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
    }
}
```

What it does:

- **Port 80** redirects to HTTPS. The site never works over plain HTTP, because the session
  cookie is HTTPS-only, and the supporter password must not travel unencrypted.
- **Port 443** forwards every request to gunicorn on `127.0.0.1:2810`. Django serves the API,
  the admin, `/static/` and the frontend, so nginx serves none of this project's files.
- `proxy_set_header Host $host` passes on the real host name. Without it, nginx sends
  `Host: 127.0.0.1:2810`, and Django answers `400 Bad Request`, because only
  `psqdb.compute.dtu.dk` is in `ALLOWED_HOSTS`.
- `proxy_set_header X-Forwarded-Proto $scheme` tells Django the request arrived over HTTPS
  (`SECURE_PROXY_SSL_HEADER` in `settings.py`).
- `root /usr/share/nginx/html` and the `error_page` lines are for nginx's own error pages,
  such as `50x.html` when gunicorn is down.

## Changes from DTU's configuration

| Change | Why |
| --- | --- |
| The port 80 server redirects to HTTPS instead of forwarding to gunicorn. | Over plain HTTP, logging in fails (the session cookie is HTTPS-only) and the supporter password would travel unencrypted. |
| `proxy_pass http://127.0.0.1:2810` instead of `http://localhost:2810`. | `localhost` can resolve to `::1` first. gunicorn only listens on `127.0.0.1`, so nginx would log a failed connection to `[::1]:2810` before falling back. |
| Removed `proxy_ssl_server_name on`. | It only applies when nginx connects to the backend over HTTPS; the connection to gunicorn is plain HTTP. |
| Removed `client_max_body_size` from the port 80 server. | That server only redirects now, so it never receives a request body. |
| Removed a doubled blank line, and indented the two `location = /...html` blocks like the `location /` block. | Readability only; nginx ignores both. |

One thing is left as DTU had it: `error_page 404 /404.html` points to `/404.html`, but the
`location` below it is `/40x.html`. This changes nothing in practice: nginx only uses
`error_page` for errors it produces itself, and 404s come from Django.

## Applying changes

Edit the file (or ask whoever manages nginx), then check and reload:

```sh
sudo nano /etc/nginx/conf.d/psqdb.conf
sudo nginx -t && sudo systemctl reload nginx
curl -sI http://psqdb.compute.dtu.dk/ | head -n 3     # expect 301 and Location: https://...
```

nginx does not need to serve any files of this project. If traffic ever grows enough for
Django's file serving to matter, add WhiteNoise to Django rather than changing nginx.
