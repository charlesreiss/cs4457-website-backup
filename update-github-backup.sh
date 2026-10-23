#!/bin/bash
bash update.sh --config _config_github.yml --destination ../../cs4457-website-temp
rsync -avz ../cs4457-website-temp/ ../cs4457-website-backup/
