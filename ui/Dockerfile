FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
COPY config.js.template /etc/nginx/templates/config.js.template

RUN static_version="$(sha256sum /usr/share/nginx/html/assets/app.css /usr/share/nginx/html/assets/app-v2.js | sha256sum | cut -c1-12)" \
    && sed -i "s/__STATIC_VERSION__/${static_version}/g" /usr/share/nginx/html/index.html

EXPOSE 80
