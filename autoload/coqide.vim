let s:current_dir = expand("<sfile>:p:h")

py3 << EOF
import logging
import os.path
import os
import sys
import vim

if not vim.eval('s:current_dir') in sys.path:
    sys.path.append(os.path.join(vim.eval('s:current_dir'), 'python'))

import coqide
EOF

if !exists('g:coqide_debug')
    let g:coqide_debug = 0
endif

if !exists('g:coqide_debug_file')
    let g:coqide_debug_file = 'coqide.log'
endif

if !exists('g:coqide_auto_close_session')
    let g:coqide_auto_close_session = 'delete'
endif

if !exists('g:coqide_no_mappings')
    let g:coqide_no_mappings = 0
endif

if !exists('g:coqide_auto_clear_message')
    let g:coqide_auto_clear_message = 1
endif

if g:coqide_debug
    execute 'py3 coqide.setup_debug_log("' . g:coqide_debug_file . '")'
endif

let s:activated = 0

function! coqide#Activate()
    if s:activated == 1
        return
    endif

    py3 ide = coqide.activate()
    let s:activated = 1

    if !exists('s:coqide_auto_deactivate')
        let s:coqide_auto_deactivate = 1
        autocmd VimLeavePre * CoqDeactivate
    endif

    command! CoqShowGoal call coqide#ShowGoal()
    command! CoqHideGoal call coqide#HideGoal()
    command! CoqToggleGoal call coqide#ToggleGoal()
    command! CoqShowMessage call coqide#ShowMessage()
    command! CoqHideMessage call coqide#HideMessage()
    command! CoqToggleMessage call coqide#ToggleMessage()

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

    call coqide#HandleEvent('Focus')
    call coqide#HandleEvent('Active')
endfunction

function! coqide#CloseSession()
    py3 ide.close_session()
endfunction

function! coqide#CloseSession()
    py3 ide.close_session()
endfunction

function! coqide#Forward()
    if g:coqide_auto_clear_message
        call coqide#ClearMessage()
    endif
    py3 ide.forward()
    call timer_start(100, 'coqide#UpdateUI')
endfunction

function! coqide#Backward()
    if g:coqide_auto_clear_message
        call coqide#ClearMessage()
    endif
    py3 ide.backward()
    call timer_start(100, 'coqide#UpdateUI')
endfunction

function! coqide#ToCursor()
    if g:coqide_auto_clear_message
        call coqide#ClearMessage()
    endif
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

function! coqide#ClearMessage()
    py3 ide.clear_message()
endfunction

function! coqide#UpdateUI(...)
    py3 ide.update_ui()
endfunction

function! coqide#HandleEvent(event)
    execute 'py3 ide.handle_event("' . a:event . '")'
endfunction

function! coqide#OnTextChanged()
    let buflen = line('$')
    let [_, cursor_line, _, _] = getpos('.')
    let saved_view = winsaveview()
    normal `[
    let [_, start_line, start_col, _] = getpos('.')
    normal `]
    let [_, end_line, _, _] = getpos('.')
    call winrestview(saved_view)

    if buflen == b:coqide_last_buflen && start_line == end_line
                \ && start_line == cursor_line
        execute 'py3 ide.edit_at('.start_line.', '.start_col.')'
    endif

    let b:coqide_last_buflen = buflen
endfunction

function! coqide#Setup()
    CoqActivate

    command! -buffer CoqNewSession call coqide#NewSession()
    command! -buffer CoqCloseSession call coqide#CloseSession()
    command! -buffer CoqForward call coqide#Forward()
    command! -buffer CoqBackward call coqide#Backward()
    command! -buffer CoqToCursor call coqide#ToCursor()
    command! -buffer CoqClearMessage call coqide#ClearMessage()

    if g:coqide_no_mappings == 0
        nnoremap <buffer> <f2> :CoqForward<cr>
        nnoremap <buffer> <f3> :CoqBackward<cr>
        nnoremap <buffer> <f4> :CoqToCursor<cr>
        inoremap <buffer> <c-e> <esc>:CoqToCursor<cr>a
    endif

    autocmd BufEnter <buffer> call coqide#HandleEvent('Focus')
    autocmd BufWinEnter <buffer> call coqide#HandleEvent('Active')
    autocmd BufWinLeave <buffer> call coqide#HandleEvent('Inactive')
    autocmd TextChanged <buffer> call coqide#OnTextChanged()
    autocmd TextChangedI <buffer> call coqide#OnTextChanged()

    if g:coqide_auto_close_session == 'unload'
        autocmd BufUnload <buffer> CoqCloseSession
    elseif g:coqide_auto_close_session == 'delete'
        autocmd BufDelete <buffer> CoqCloseSession
    else
        echoerr 'g:coqide_auto_close_session must be "unload" or "delete"'
        autocmd BufDelete <buffer> CoqCloseSession
    endif

    CoqNewSession

    let b:coqide_last_buflen = line('$')
endfunction

command! CoqActivate call coqide#Activate()
command! CoqDeactivate call coqide#Deactivate()

hi default CoqStcProcessing ctermbg=147 guibg=#AAAAFF
hi default CoqStcProcessed ctermbg=22 guibg=#2F5C00
hi default CoqStcAxiom ctermbg=227 guibg=#E8ED51
hi link CoqStcError Error
