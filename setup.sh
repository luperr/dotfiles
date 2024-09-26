#!/bin/bash

# Set some default vars

DOTFILES_DIR=$HOME/dotfiles
PACKAGES_DIR=$DOTFILES_DIR/packages

# Install updates and default apt packages

PACKAGES=$(cat $PACKAGES_DIR/apt.txt | sort -u)
sudo apt-get -q update && sudo apt-get -q upgrade -y
echo $PACKAGES | xargs sudo apt-get -q install -y

# Install AWS CLI
TEMPDIR=$(mktemp -d)
pushd $TEMPDIR
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-$ARCH.zip" -o "awscliv2.zip"
unzip -qq -o awscliv2.zip
sudo ./aws/install -u
popd

# Setup Git global config....
git config --global user.name luperr
git config --global user.email lachlannwhitehill@gmail.com


# Get Repo for bashrc plugin..... Move to Bashrc file? 
git clone https://github.com/magicmonty/bash-git-prompt.git ~/.bash-git-prompt --depth=1



# Set local user into docker group
sudo usermod -a -G docker $USER


