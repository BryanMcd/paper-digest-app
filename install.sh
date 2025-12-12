#!/bin/bash
echo "Installing paper-digest-app..."
chmod +x run_paperdigest.sh
sudo ln -sf "$(pwd)/run_paperdigest.sh" /usr/local/bin/paperdigest
echo "Done! Type 'paperdigest' to start."