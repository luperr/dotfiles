#Must have alias
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Add the git prompt if needed
if "test ! -d ~/.bash-git-prompt" \
	"run 'git clone https://github.com/magicmonty/bash-git-prompt.git ~/.bash-git-prompt --depth=1'"

#Add git to the terminal
if [ -f "$HOME/.bash-git-prompt/gitprompt.sh" ]; then
	GIT_PROMPT_ONLY_IN_REPO=1
	source "$HOME/.bash-git-prompt/gitprompt.sh"
fi
