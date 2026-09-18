# Schools in Reach: static site served by nginx on Railway ($PORT is set by Railway).
FROM nginx:1.27-alpine
ENV PORT=8080
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY site /usr/share/nginx/html
