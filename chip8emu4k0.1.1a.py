"""chip 8 emulator 0.1 - single-file Tkinter CHIP-8 emulator."""

import random
import tkinter as tk
from tkinter import filedialog, messagebox

WIDTH = 64
HEIGHT = 32
SCALE = 10
CPU_HZ = 600
TIMER_HZ = 60
FRAME_MS = int(1000 / 60)
CYCLES_PER_FRAME = max(1, CPU_HZ // 60)

BG = "black"
FG = "blue"
PIXEL_ON = "blue"
PIXEL_OFF = "black"

FONT_SET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
    0x20, 0x60, 0x20, 0x20, 0x70,  # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
    0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
    0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
    0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
    0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
    0xF0, 0x80, 0xF0, 0x80, 0x80,  # F
]

KEYMAP = {
    "1": 0x1, "2": 0x2, "3": 0x3, "4": 0xC,
    "q": 0x4, "w": 0x5, "e": 0x6, "r": 0xD,
    "a": 0x7, "s": 0x8, "d": 0x9, "f": 0xE,
    "z": 0xA, "x": 0x0, "c": 0xB, "v": 0xF,
}


class Chip8:
    def __init__(self):
        self.reset()

    def reset(self):
        self.memory = bytearray(4096)
        for i, b in enumerate(FONT_SET):
            self.memory[0x50 + i] = b
        self.V = bytearray(16)
        self.I = 0
        self.pc = 0x200
        self.stack = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.display = [[0] * WIDTH for _ in range(HEIGHT)]
        self.keys = [0] * 16
        self.draw_flag = True
        self.waiting_for_key = None  # register index, or None

    def load_rom(self, data: bytes):
        self.reset()
        if len(data) > 4096 - 0x200:
            raise ValueError("ROM too large for CHIP-8 memory")
        for i, b in enumerate(data):
            self.memory[0x200 + i] = b

    def tick_timers(self):
        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1

    def cycle(self):
        if self.waiting_for_key is not None:
            # FX0A behavior: block until any key is pressed
            for k, pressed in enumerate(self.keys):
                if pressed:
                    self.V[self.waiting_for_key] = k
                    self.waiting_for_key = None
                    break
            else:
                return

        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc = (self.pc + 2) & 0xFFF
        self._execute(opcode)

    def _execute(self, opcode):
        nnn = opcode & 0x0FFF
        nn = opcode & 0x00FF
        n = opcode & 0x000F
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        head = opcode & 0xF000

        if opcode == 0x00E0:
            self.display = [[0] * WIDTH for _ in range(HEIGHT)]
            self.draw_flag = True
        elif opcode == 0x00EE:
            self.pc = self.stack.pop() if self.stack else self.pc
        elif head == 0x1000:
            self.pc = nnn
        elif head == 0x2000:
            self.stack.append(self.pc)
            self.pc = nnn
        elif head == 0x3000:
            if self.V[x] == nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif head == 0x4000:
            if self.V[x] != nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif head == 0x5000 and n == 0:
            if self.V[x] == self.V[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif head == 0x6000:
            self.V[x] = nn
        elif head == 0x7000:
            self.V[x] = (self.V[x] + nn) & 0xFF
        elif head == 0x8000:
            self._exec_8(x, y, n)
        elif head == 0x9000 and n == 0:
            if self.V[x] != self.V[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif head == 0xA000:
            self.I = nnn
        elif head == 0xB000:
            self.pc = (nnn + self.V[0]) & 0xFFF
        elif head == 0xC000:
            self.V[x] = random.randint(0, 255) & nn
        elif head == 0xD000:
            self._draw_sprite(self.V[x], self.V[y], n)
        elif head == 0xE000:
            if nn == 0x9E:
                if self.keys[self.V[x] & 0xF]:
                    self.pc = (self.pc + 2) & 0xFFF
            elif nn == 0xA1:
                if not self.keys[self.V[x] & 0xF]:
                    self.pc = (self.pc + 2) & 0xFFF
        elif head == 0xF000:
            self._exec_f(x, nn)

    def _exec_8(self, x, y, n):
        if n == 0x0:
            self.V[x] = self.V[y]
        elif n == 0x1:
            self.V[x] |= self.V[y]
        elif n == 0x2:
            self.V[x] &= self.V[y]
        elif n == 0x3:
            self.V[x] ^= self.V[y]
        elif n == 0x4:
            total = self.V[x] + self.V[y]
            self.V[0xF] = 1 if total > 0xFF else 0
            self.V[x] = total & 0xFF
        elif n == 0x5:
            self.V[0xF] = 1 if self.V[x] >= self.V[y] else 0
            self.V[x] = (self.V[x] - self.V[y]) & 0xFF
        elif n == 0x6:
            self.V[0xF] = self.V[x] & 0x1
            self.V[x] >>= 1
        elif n == 0x7:
            self.V[0xF] = 1 if self.V[y] >= self.V[x] else 0
            self.V[x] = (self.V[y] - self.V[x]) & 0xFF
        elif n == 0xE:
            self.V[0xF] = (self.V[x] & 0x80) >> 7
            self.V[x] = (self.V[x] << 1) & 0xFF

    def _exec_f(self, x, nn):
        if nn == 0x07:
            self.V[x] = self.delay_timer
        elif nn == 0x0A:
            self.waiting_for_key = x
        elif nn == 0x15:
            self.delay_timer = self.V[x]
        elif nn == 0x18:
            self.sound_timer = self.V[x]
        elif nn == 0x1E:
            self.I = (self.I + self.V[x]) & 0xFFF
        elif nn == 0x29:
            self.I = 0x50 + (self.V[x] & 0xF) * 5
        elif nn == 0x33:
            v = self.V[x]
            self.memory[self.I] = v // 100
            self.memory[self.I + 1] = (v // 10) % 10
            self.memory[self.I + 2] = v % 10
        elif nn == 0x55:
            for i in range(x + 1):
                self.memory[self.I + i] = self.V[i]
        elif nn == 0x65:
            for i in range(x + 1):
                self.V[i] = self.memory[self.I + i]

    def _draw_sprite(self, vx, vy, height):
        vx &= 0xFF
        vy &= 0xFF
        self.V[0xF] = 0
        for row in range(height):
            sprite = self.memory[(self.I + row) & 0xFFF]
            py = (vy + row) % HEIGHT
            for col in range(8):
                if sprite & (0x80 >> col):
                    px = (vx + col) % WIDTH
                    if self.display[py][px] == 1:
                        self.V[0xF] = 1
                    self.display[py][px] ^= 1
        self.draw_flag = True


class Chip8App:
    def __init__(self, root):
        self.root = root
        self.root.title("chip 8 emu 0.1.1a")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.cpu = Chip8()
        self.rom_data = None
        self.running = False
        self.pixel_ids = [[None] * WIDTH for _ in range(HEIGHT)]
        self._loop_after_id = None

        self._build_ui()
        self._bind_keys()
        self._draw_full()

    def _build_ui(self):
        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_opts = dict(
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
            highlightbackground=BG, highlightcolor=FG, bd=1, relief=tk.RAISED,
        )

        self.load_btn = tk.Button(toolbar, text="Load ROM", command=self.load_rom, **btn_opts)
        self.load_btn.pack(side=tk.LEFT, padx=4, pady=4)

        self.pause_btn = tk.Button(toolbar, text="Pause", command=self.toggle_pause, **btn_opts)
        self.pause_btn.pack(side=tk.LEFT, padx=4, pady=4)

        self.reset_btn = tk.Button(toolbar, text="Reset", command=self.reset_rom, **btn_opts)
        self.reset_btn.pack(side=tk.LEFT, padx=4, pady=4)

        self.status = tk.Label(
            toolbar, text="No ROM loaded", bg=BG, fg=FG, anchor="w",
        )
        self.status.pack(side=tk.LEFT, padx=8)

        self.canvas = tk.Canvas(
            self.root,
            width=WIDTH * SCALE,
            height=HEIGHT * SCALE,
            bg=PIXEL_OFF,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.TOP)

        for y in range(HEIGHT):
            for x in range(WIDTH):
                x0, y0 = x * SCALE, y * SCALE
                self.pixel_ids[y][x] = self.canvas.create_rectangle(
                    x0, y0, x0 + SCALE, y0 + SCALE,
                    fill=PIXEL_OFF, outline=PIXEL_OFF,
                )

    def _bind_keys(self):
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_key_press(self, event):
        k = KEYMAP.get(event.keysym.lower())
        if k is not None:
            self.cpu.keys[k] = 1

    def _on_key_release(self, event):
        k = KEYMAP.get(event.keysym.lower())
        if k is not None:
            self.cpu.keys[k] = 0

    def load_rom(self):
        path = filedialog.askopenfilename(
            title="Open CHIP-8 ROM",
            filetypes=[("CHIP-8 ROM", "*.ch8 *.c8 *.rom"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.cpu.load_rom(data)
            self.rom_data = data
            self.running = True
            self.pause_btn.config(text="Pause")
            self.status.config(text=f"Running: {path.split('/')[-1]}")
            self._draw_full()
            self._start_loop()
        except Exception as e:
            messagebox.showerror("Load ROM failed", str(e))

    def reset_rom(self):
        if self.rom_data is None:
            self.cpu.reset()
            self._draw_full()
            self.status.config(text="No ROM loaded")
            return
        self.cpu.load_rom(self.rom_data)
        self.running = True
        self.pause_btn.config(text="Pause")
        self._draw_full()

    def toggle_pause(self):
        if self.rom_data is None:
            return
        self.running = not self.running
        self.pause_btn.config(text="Pause" if self.running else "Resume")
        if self.running:
            self._start_loop()

    def _start_loop(self):
        if self._loop_after_id is None:
            self._loop_after_id = self.root.after(FRAME_MS, self._frame)

    def _frame(self):
        self._loop_after_id = None
        if self.running:
            for _ in range(CYCLES_PER_FRAME):
                self.cpu.cycle()
            self.cpu.tick_timers()
            if self.cpu.draw_flag:
                self._draw_full()
                self.cpu.draw_flag = False
        if self.running:
            self._loop_after_id = self.root.after(FRAME_MS, self._frame)

    def _draw_full(self):
        for y in range(HEIGHT):
            row = self.cpu.display[y]
            for x in range(WIDTH):
                color = PIXEL_ON if row[x] else PIXEL_OFF
                self.canvas.itemconfig(self.pixel_ids[y][x], fill=color, outline=color)

    def _on_close(self):
        self.running = False
        if self._loop_after_id is not None:
            try:
                self.root.after_cancel(self._loop_after_id)
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    Chip8App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
