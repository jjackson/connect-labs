FROM python:3.11-slim-bookworm as build-python
RUN apt-get update \
  # dependencies for building Python packages
  # libgdal-dev needed for GeoDjango/GDAL bindings
  # libproj-dev needed for pyproj (geopandas dependency)
  # libgeos-dev needed for shapely
  # cargo/rustc needed for temporalio (pydantic-ai dependency)
  && apt-get install -y build-essential libpq-dev libgdal-dev libproj-dev libgeos-dev cargo rustc
COPY ./requirements /requirements
# Build wheels for each requirement file separately to avoid conflicts
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r /requirements/base.txt
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r /requirements/labs.txt

FROM node:18-bullseye AS build-node
#RUN apt-get update && apt-get -y install curl
#RUN curl -sL https://deb.nodesource.com/setup_18.x | bash -
#RUN apt-get install -y nodejs
RUN nodejs -v && npm -v
WORKDIR /app
COPY . /app
RUN npm install
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1
ENV DEBUG=0

RUN apt-get update \
  # psycopg2, gettext etc dependencies
  # gdal-bin provides GDAL runtime libraries for GeoDjango spatial features
  && apt-get install -y libpq-dev gettext curl gdal-bin \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

RUN addgroup --system django \
    && adduser --system --ingroup django django

ENV DJANGO_SETTINGS_MODULE=config.settings.labs_aws

COPY --from=build-node /app/commcare_connect/static/bundles /app/commcare_connect/static/bundles
COPY --from=build-python /wheels /wheels
COPY ./requirements /requirements
# Install sequentially: base, then labs (which may upgrade packages)
RUN pip install --no-index --find-links=/wheels -r /requirements/base.txt && \
    pip install --no-index --find-links=/wheels -r /requirements/labs.txt --force-reinstall \
    && rm -rf /wheels \
    && rm -rf /root/.cache/pip/*

WORKDIR /app

COPY ./docker/* /
RUN chmod +x /entrypoint /start*
RUN chown django /entrypoint /start*

ARG APP_RELEASE="dev"
ENV APP_RELEASE=${APP_RELEASE}

COPY --chown=django:django . /app

RUN python /app/manage.py collectstatic --noinput
RUN chown django:django -R staticfiles

USER django

EXPOSE 8000

ENTRYPOINT ["/entrypoint"]
