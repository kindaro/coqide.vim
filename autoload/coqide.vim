let s:current_dir = expand("<sfile>:p:h")

py3 << EOF
import logging
import os.path
import os
import sys
import vim

if not vim.eval('s:current_dir') in sys.path:
    sys.path.append(os.path.join(vim.eval('s:current_dir'), 'python'))

from coqide.plugin import Plugin

plugin = Plugin()
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
    execute 'py3 plugin.setup_debug_log("' . g:coqide_debug_file . '")'
endif

let s:activated = 0

function! coqide#Activate()
    if s:activated == 1
        return
    endif

    let s:activated = 1

    autocmd VimLeavePre * call coqide#Deactivate()
    command! CoqNewSession call coqide#NewSession()
    command! CoqCloseSession call coqide#CloseSession()
    command! CoqForward call coqide#Forward()
    command! CoqBackward call coqide#Backward()
    command! CoqToCursor call coqide#ToCursor()
    command! CoqClearMessages call coqide#ClearMessages()
    command! CoqShowGoal call coqide#ShowGoal()
    command! CoqHideGoal call coqide#HideGoal()
    command! CoqToggleGoal call coqide#ToggleGoal()
    command! CoqShowMessage call coqide#ShowMessage()
    command! CoqHideMessage call coqide#HideMessage()
    command! CoqToggleMessage call coqide#ToggleMessage()

    let s:update_timer = timer_start(300, 'coqide#ProcessFeedbacks',
                \ { 'repeat': -1 })
endfunction

function! coqide#Deactivate()
    if s:activated == 0
        return
    endif

    py3 plugin.cleanup()
    let s:activated = 0

    call timer_stop(s:update_timer)

    delcommand CoqNewSession
    delcommand CoqCloseSession
    delcommand CoqForward
    delcommand CoqBackward
    delcommand CoqToCursor
    delcommand CoqClearMessages
    delcommand CoqShowGoal
    delcommand CoqHideGoal
    delcommand CoqToggleGoal
    delcommand CoqShowMessage
    delcommand CoqHideMessage
    delcommand CoqToggleMessage
endfunction

function! coqide#NewSession()
    py3 plugin.new_session()
endfunction

function! coqide#CloseSession()
    py3 plugin.close_session()
endfunction

function! coqide#Forward()
    if g:coqide_auto_clear_message
        call coqide#ClearMessages()
    endif
    py3 plugin.forward()
    call timer_start(100, 'coqide#ProcessFeedbacks')
endfunction

function! coqide#Backward()
    if g:coqide_auto_clear_message
        call coqide#ClearMessages()
    endif
    py3 plugin.backward()
    call timer_start(100, 'coqide#ProcessFeedbacks')
endfunction

function! coqide#ToCursor()
    if g:coqide_auto_clear_message
        call coqide#ClearMessages()
    endif
    py3 plugin.to_cursor()
    call timer_start(100, 'coqide#ProcessFeedbacks')
endfunction

function! coqide#Focus()
    py3 plugin.focus()
endfunction

function! coqide#SetActive()
    py3 plugin.set_active()
endfunction

function! coqide#SetInactive()
    py3 plugin.set_inactive()
endfunction

function! coqide#CreateWindow(name, filetype, split_method)
    execute a:split_method . " " . a:name
    setlocal buftype=nofile
    setlocal noswapfile
    setlocal bufhidden=delete
    setlocal nospell
    setlocal nonumber
    setlocal norelativenumber
    setlocal nocursorline
    setlocal nomodifiable
    setlocal nobuflisted
    execute "setlocal filetype=" . a:filetype
endfunction

function! coqide#ShowGoals()
    if bufwinnr('^/Goals/$') != -1
        return
    endif

    let messages_winnr = bufwinnr('^/Messages/$')
    if  messages_winnr != -1
        " Create the goal window above the message window.
        execute messages_winnr . 'wincmd w'
        call coqide#CreateWindow('/Goals/', 'coq-goals', 'leftabove new')
    else
        call coqide#CreateWindow('/Goals/', 'coq-goals', 'rightbelow vnew')
    endif

    py3 plugin.redraw_goals()
endfunction

function! coqide#HideGoals()
    if bufwinnr('^/Goals/$') == -1
        return
    endif

    goals_bufnr = bufnr('^/Goals/$')
    execute goals_bufnr . 'bdelete'
endfunction

function! coqide#ToggleGoals()
    if bufwinnr('^/Goals/$') != -1
        call coqide#HideGoals()
    else
        call coqide#ShowGoals()
    endif
endfunction

function! coqide#ShowMessage()
    if bufwinnr('^/Messages/$') != -1
        return
    endif

    let goals_winnr = bufwinnr('^/Goals/$')
    if  goals_winnr != -1
        " Create the messages window below the goals window.
        execute goals_winnr . 'wincmd w'
        call coqide#CreateWindow('/Messages/', 'coq-messages', 'rightbelow new')
    else
        call coqide#CreateWindow('/Messages/', 'coq-messages', 'rightbelow vnew')
    endif

    py3 plugins.redraw_messages()
endfunction

function! coqide#HideMessage()
    if bufwinnr('^/Messages/$') == -1
        return
    endif

    messages_bufnr = bufnr('^/Messages/$')
    execute messages_bufnr . 'bdelete'
endfunction

function! coqide#ToggleMessage()
    if bufwinnr('^/Messages/$') != -1
        call coqide#HideMessages()
    else
        call coqide#ShowMessages()
    endif
endfunction

function! coqide#ClearMessages()
    py3 plugin.clear_messages()
endfunction

function! coqide#ProcessFeedbacks(...)
    py3 plugin.process_feedbacks()
endfunction

function! coqide#OnTextChanged()
    return
    let buflen = line('$')
    let saved_view = winsaveview()
    let [_, cursor_line, _, _] = getpos('.')
    normal `[
    let [_, start_line, start_col, _] = getpos('.')
    normal `]
    let [_, end_line, _, _] = getpos('.')

    if buflen == b:coqide_last_buflen && start_line == end_line
                \ && start_line == cursor_line
        execute 'py3 ide.edit_at('.start_line.', '.start_col.')'
    else
        silent undo
        let g:coqide_buffer_prev = getbufline('%', 1, '$')
        silent redo
        py3 ide.apply_text_changes()
    endif

    call winrestview(saved_view)
    let b:coqide_last_buflen = buflen
endfunction

function! coqide#Setup()
    call coqide#Activate()

    if g:coqide_no_mappings == 0
        nnoremap <buffer> <f2> :CoqForward<cr>
        nnoremap <buffer> <f3> :CoqBackward<cr>
        nnoremap <buffer> <f4> :CoqToCursor<cr>
        inoremap <buffer> <f2> <esc>:CoqForward<cr>a
        inoremap <buffer> <f3> <esc>:CoqBackward<cr>a
        inoremap <buffer> <f4> <esc>:CoqToCursor<cr>a
    endif

    autocmd BufEnter <buffer> call coqide#Focus()
    autocmd BufWinEnter <buffer> call coqide#SetActive()
    autocmd BufWinLeave <buffer> call coqide#SetInactive()
    " autocmd TextChanged <buffer> call coqide#OnTextChanged()
    " autocmd TextChangedI <buffer> call coqide#OnTextChanged()

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

hi default CoqStcSent ctermbg=147 guibg=#AAAAFF
hi default CoqStcAxiom ctermbg=227 guibg=#E8ED51
hi default CoqStcVerified ctermbg=22 guibg=#2F5C00
hi link CoqStcError Error
