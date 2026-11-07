# School Money (money.schoolsinreach.com): static site served by nginx on Railway ($PORT is set by Railway).
# The site ships as one zstd archive: 24,808 near-identical school pages compress to about 105 MB with a long
# match window, against about 350 MB as the gzip tarball `railway up` makes of the loose files, which Railway
# refuses ("413 Payload Too Large"). Unpack it in a throwaway stage so the archive never reaches the final image.
FROM alpine:3.20 AS site
RUN apk add --no-cache zstd tar
COPY site.tar.zst /tmp/site.tar.zst
RUN mkdir /site && zstd -d --long=30 -c /tmp/site.tar.zst | tar -xf - -C /site

FROM nginx:1.27-alpine
ENV PORT=8080
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=site /site /usr/share/nginx/html
