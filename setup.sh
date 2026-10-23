#!/bin/bash
BUNDLE=bundle
$BUNDLE config set --local path vendor/bundle
$BUNDLE install
