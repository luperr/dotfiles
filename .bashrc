#Must have alias
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'


#Add git to the terminal
if [ -f "$HOME/.bash-git-prompt/gitprompt.sh" ]; then
	GIT_PROMPT_ONLY_IN_REPO=1
	source "$HOME/.bash-git-prompt/gitprompt.sh"
fi
