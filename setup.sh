#!/bin/bash

# Set some default vars

DOTFILES_DIR=$HOME/dotfiles
PACKAGES_DIR=$DOTFILES_DIR/packages

#Dertmine Operating system

case $(uname | tr '[:upper:]' '[:lower:]') in
linux*)
  export PACKAGE_MANAGER='apt'
  export HOST_OS='linux'
  ;;
darwin*)
  export PACKAGE_MANAGER='homebrew'
  export HOST_OS='mac'
  ;;
*)
  export PACKAGE_MANAGER=''
  export HOST_OS=''
  ;;
esac

echo $PACKAGE_MANAGER $HOST_OS

exit

function lazy_vim_install ()

TODO: paraterise and use system agnostic package manager..... like homebrew, apt or yum (TBH still think NIX would be a good default packagemanager without using NixOS)
# Install updates and default apt packages
PACKAGES=$(cat $PACKAGES_DIR/apt.txt | sort -u)
sudo apt-get -q update && sudo apt-get -q upgrade -y
echo $PACKAGES | xargs sudo apt-get -q install -y

# Setup Git global config....
git config --global user.name luperr
git config --global user.email lachlannwhitehill@gmail.com
#TODO: more useful default git stuff. Like the flobal merger resolve setting.

# Get Repo for bashrc plugin..... Move to Bashrc file?
git clone https://github.com/magicmonty/bash-git-prompt.git ~/.bash-git-prompt --depth=1

#TODO: append the .bashrc file
#create the .tmux.conf
#append the .bashrc file
#VIM goodies

# Set local user into docker group
sudo usermod -a -G docker $USER
