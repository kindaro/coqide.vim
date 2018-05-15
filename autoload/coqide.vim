let s:current_dir = expand("<sfile>:p:h")

py3 << EOF
import logging
import os.path
import os
import sys
import vim

if not vim.eval('s:current_dir') in sys.path:
    sys.path.append(os.path.join(vim.eval('s:current_dir'), 'python'))
EOF

execute 'py3 logging.basicConfig(level="DEBUG", filename="/Users/tding/coqtop.log")'
py3 import coqide

let s:activated = 0

function! coqide#Activate()
    if s:activated == 1
        return
    endif

    py3 ide = coqide.activate()
    let s:activated = 1

    command! CoqShowGoal call coqide#ShowGoal
    command! CoqHideGoal call coqide#HideGoal
    command! CoqToggleGoal call coqide#ToggleGoal
    command! CoqShowMessage call coqide#ShowMessage
    command! CoqHideMessage call coqide#HideMessage
    command! CoqToggleMessage call coqide#ToggleMessage
    command! CoqUpdateUI call coqide#UpdateUI()

    let s:update_timer = timer_start(300, 'coqide#UpdateUI',
                \ { 'repeat': -1 })
endfunction

function! coqide#Deactivate()
    if s:activated == 0
        return
    endif

    py3 ide.deactivate()
    py3 ide = None
    let s:activated = 0

    call timer_stop(s:update_timer)

    delcommand CoqShowGoal
    delcommand CoqHideGoal
    delcommand CoqToggleGoal
    delcommand CoqShowMessage
    delcommand CoqHideMessage
    delcommand CoqToggleMessage
endfunction

function! coqide#NewSession()
    py3 ide.new_session()
endfunction

function! coqide#CloseSession()
    py3 ide.close_session()
endfunction

function! coqide#CloseSession()
    py3 ide.close_session()
endfunction

function! coqide#Forward()
    py3 ide.forward()
    call timer_start(100, 'coqide#UpdateUI')
endfunction

function! coqide#Backward()
    py3 ide.backward()
    call timer_start(100, 'coqide#UpdateUI')
endfunction

function! coqide#ToCursor()
    py3 ide.to_cursor()
    call timer_start(100, 'coqide#UpdateUI')
endfunction

function! coqide#ShowGoal()
    py3 ide.set_goal_visibility('show')
endfunction

function! coqide#HideGoal()
    py3 ide.set_goal_visibility('hide')
endfunction

function! coqide#ToggleGoal()
    py3 ide.set_goal_visibility('toggle')
endfunction

function! coqide#ShowMessage()
    py3 ide.set_message_visibility('show')
endfunction

function! coqide#HideMessage()
    py3 ide.set_message_visibility('hide')
endfunction

function! coqide#ToggleMessage()
    py3 ide.set_message_visibility('toggle')
endfunction

function! coqide#UpdateUI(...)
    py3 ide.update_ui()
endfunction

function! coqide#Setup()
    command! CoqActivate call coqide#Activate()
    command! CoqDeactivate call coqide#Deactivate()

    CoqActivate

    command! -buffer CoqNewSession call coqide#NewSession()
    command! -buffer CoqCloseSession call coqide#CloseSession()
    command! -buffer CoqForward call coqide#Forward()
    command! -buffer CoqBackward call coqide#Backward()
    command! -buffer CoqToCursor call coqide#ToCursor()

    noremap <buffer> <f2> :CoqForward<cr>
    noremap <buffer> <f3> :CoqBackward<cr>
    noremap <buffer> <f4> :CoqToCursor<cr>

    setlocal bufhidden=hide
    hi default CoqStcProcessing ctermbg=60 guibg=LimeGreen
    hi default CoqStcProcessed ctermbg=17 guibg=LightGreen
    hi default CoqStcAxiom ctermbg=14 guibg=Yellow
    hi link CoqStcError Error

    autocmd! BufUnload <buffer> CoqCloseSession

    CoqNewSession
endfunction
