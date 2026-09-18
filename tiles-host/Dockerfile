# Static host for the Schools in Reach basemap (Protomaps PMTiles, read by browsers with HTTP range requests).
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY tiles /usr/share/nginx/html/tiles
RUN printf 'ok\n' > /usr/share/nginx/html/health
EXPOSE 80
