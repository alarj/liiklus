FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
COPY config.js.template /etc/nginx/templates/config.js.template

EXPOSE 80
