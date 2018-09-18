# CoqIDE

## Requirements

Vim8/Neovim compiled with Python3 support. You can check by using `echo has('python3')`

## Installation
For vim-plugged users, paste the following line into your .vimrc :

    Plug 'iandingx/coqide.vim'

## Why CoqIDE?
This plugin is for Coq programming as a counterpart of CoqIDE in Vim.

Besides Coq syntax highlighting, it supports the following features:

- Asynchronous proofs: Vim won't be stuck when validating the proofs.
- Multi-buffer editing: You can edit more than one Coq buffer at the same time
  in a Vim instance.
- Window toggling: You can show or hide the Goal and Message window.

## Basic Usage
For the full documentation, please run `:help coqide` in Vim or read the file
doc/coqide.txt online.

### :CoqForward
Process the next command.

The default binding is `<f2>`.

### :CoqBackward
Go back to the previous state.

The default binding is `<f3>`.

### :CoqToCursor
Process until the command under the cursor if the cursor is ahead of the last
processed command in the buffer, or go back to the state of the sentence under
the cursor if the cursor is behind the last processed command.

The default binding is `<f4>`.
