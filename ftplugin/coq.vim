if !exists('b:coqide_setup_flag')
    let b:coqide_setup_flag = 1
    call coqide#Setup()
endif
