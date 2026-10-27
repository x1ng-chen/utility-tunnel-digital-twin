ENTRY(test_entry)
MEMORY {
  FLASH (rx) : ORIGIN = 0x00010000, LENGTH = 1M
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 512K
}
SECTIONS {
  .text : { *(.text*) *(.rodata*) *(.ARM.extab*) *(.ARM.exidx*) } > FLASH
  .data : { *(.data*) } > RAM
  .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
  . = ALIGN(8);
  end = .;
}
