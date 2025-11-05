

import pygame
import math
import csv
from datetime import datetime
import sys
import random


# Constants & Defaults

pygame.init()
CLOCK = pygame.time.Clock()
FPS = 60

# Physics
G_EARTH = 9.81  # m/s^2
AIR_DENSITY = 1.225  # kg/m^3 (sea level)
DRAG_COEFF = 0.47  # sphere approx

# Display - auto detect resolution and take 90%
info = pygame.display.Info()
SCREEN_W, SCREEN_H = info.current_w, info.current_h
WIDTH = int(SCREEN_W * 0.9)
HEIGHT = int(SCREEN_H * 0.9)

# Colors (dark theme)
BG = (18, 20, 25)
PANEL = (30, 34, 42)
PANEL_BORDER = (60, 66, 78)
TEXT = (230, 230, 235)
ACCENT = (90, 160, 255)
GOOD = (100, 210, 130)
BAD = (255, 110, 110)
GRID = (45, 50, 60)
TRAJECTORY_COLORS = [
    (255, 120, 120), (120, 200, 255), (160, 120, 255),
    (255, 210, 120), (120, 255, 180), (240, 140, 255),
]

# Base UI design resolution for scaling
BASE_W, BASE_H = 1600, 900


# Utility / Helpers

def clamp(v, a, b): return max(a, min(b, v))

def gen_color():
    return random.choice(TRAJECTORY_COLORS)


# Projectile model

class Projectile:
    def __init__(self, angle_deg, speed, mass, y0, air_resistance=True, color=None):
        self.angle = math.radians(angle_deg)
        self.v0 = float(speed)
        self.mass = float(mass)
        self.y0 = float(y0)
        self.air = bool(air_resistance)

        self.vx = self.v0 * math.cos(self.angle)
        self.vy = self.v0 * math.sin(self.angle)
        self.x = 0.0  # start at origin horizontally
        self.y = self.y0

        self.t = 0.0
        self.dt = 0.01  # integration time step for physics (s)

        self.trajectory = [(self.t, self.x, self.y)]
        self.landed = False

        self.max_height = self.y0
        self.final_speed = 0.0
        self.flight_time = 0.0
        self.range = 0.0

        self.color = color if color else gen_color()


        try:
            volume = self.mass / 1000.0
            if volume <= 0:
                self.area = 0.01
            else:
                radius = (3 * volume / (4 * math.pi)) ** (1.0 / 3.0)
                self.area = math.pi * radius * radius
        except Exception:
            self.area = 0.01

    def step(self):
        if self.landed:
            return

        dt = self.dt

        # Speed magnitude
        v = math.hypot(self.vx, self.vy)

        if self.air and v > 0:
            drag_force = 0.5 * AIR_DENSITY * DRAG_COEFF * self.area * v * v
            ax = - (drag_force * (self.vx / v)) / self.mass
            ay = - (drag_force * (self.vy / v)) / self.mass - G_EARTH
        else:
            ax = 0.0
            ay = -G_EARTH

        # Euler integration
        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.t += dt

        # store trajectory
        self.trajectory.append((self.t, self.x, self.y))

        # update metrics
        if self.y > self.max_height:
            self.max_height = self.y

        # landing check (when crosses y <= 0)
        if self.y <= 0:
            # interpolate between last two points for more accurate landing time/x
            t2, x2, y2 = self.trajectory[-1]
            t1, x1, y1 = self.trajectory[-2]
            if y2 == y1:
                frac = 0.0
            else:
                frac = (0 - y1) / (y2 - y1)
            frac = clamp(frac, 0.0, 1.0)
            t_land = t1 + frac * (t2 - t1)
            x_land = x1 + frac * (x2 - x1)
            # final speed approximate from last velocities
            self.flight_time = t_land
            self.range = x_land
            # compute final speed magnitude using vx, vy at last step (approx)
            self.final_speed = math.hypot(self.vx, self.vy)
            self.landed = True
            # keep final point at y = 0
            self.trajectory[-1] = (t_land, x_land, 0.0)


# UI Widgets 

class TextField:
    def __init__(self, label, text, font, rect, scale):
        self.label = label
        self.text = str(text)
        self.font = font
        self.rect = pygame.Rect(rect)
        self.active = False
        self.cursor_timer = 0
        self.scale = scale

    def draw(self, surf):
        # label
        label_surf = self.font.render(self.label, True, TEXT)
        surf.blit(label_surf, (self.rect.x, self.rect.y - int(22 * self.scale)))

        # box
        pygame.draw.rect(surf, (18, 20, 25), self.rect, border_radius=int(6 * self.scale))  # inner dark
        pygame.draw.rect(surf, PANEL_BORDER if self.active else (55, 60, 70), self.rect, 2, border_radius=int(6 * self.scale))

        # text
        txt = self.font.render(self.text, True, TEXT)
        surf.blit(txt, (self.rect.x + int(8 * self.scale), self.rect.y + int(6 * self.scale)))

        # cursor
        if self.active:
            self.cursor_timer += 1
            if self.cursor_timer % 60 < 30:
                cursor_x = self.rect.x + int(8 * self.scale) + txt.get_width() + 2
                pygame.draw.line(surf, TEXT, (cursor_x, self.rect.y + int(6 * self.scale)), (cursor_x, self.rect.y + int(22 * self.scale)), 2)

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(ev.pos)
            self.cursor_timer = 0

        if self.active and ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_TAB):
                self.active = False
            elif ev.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                # allow digits, decimal point, minus
                if ev.unicode in '0123456789.-':
                    if ev.unicode == '.' and '.' in self.text:
                        return
                    if ev.unicode == '-' and (len(self.text) > 0 or '-' in self.text):
                        return
                    self.text += ev.unicode

    def get_value(self):
        try:
            return float(self.text)
        except Exception:
            return 0.0

    def set_rect(self, rect, scale):
        self.rect = pygame.Rect(rect)
        self.scale = scale

class Button:
    def __init__(self, text, font, rect, color_primary, scale):
        self.text = text
        self.font = font
        self.rect = pygame.Rect(rect)
        self.color = color_primary
        self.hover = False
        self.scale = scale

    def draw(self, surf):
        base = tuple(min(255, c + 20) for c in self.color) if self.hover else self.color
        pygame.draw.rect(surf, base, self.rect, border_radius=int(8 * self.scale))
        pygame.draw.rect(surf, PANEL_BORDER, self.rect, 2, border_radius=int(8 * self.scale))
        ts = self.font.render(self.text, True, (18, 20, 25))
        surf.blit(ts, ts.get_rect(center=self.rect.center))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(ev.pos):
            return True
        return False

    def set_rect(self, rect, scale):
        self.rect = pygame.Rect(rect)
        self.scale = scale

class Toggle:
    def __init__(self, label, font, rect, on=False, scale=1.0):
        self.label = label
        self.font = font
        self.rect = pygame.Rect(rect)
        self.on = on
        self.scale = scale

    def draw(self, surf):
        # label
        lbl = self.font.render(self.label, True, TEXT)
        surf.blit(lbl, (self.rect.x, self.rect.y - int(22 * self.scale)))
        # toggle box
        box = pygame.Rect(self.rect.x, self.rect.y, int(40 * self.scale), int(24 * self.scale))
        pygame.draw.rect(surf, (45, 50, 60), box, border_radius=int(12 * self.scale))
        if self.on:
            handle_x = box.x + box.w - int(18 * self.scale)
            pygame.draw.rect(surf, GOOD, (handle_x, box.y + int(4 * self.scale), int(14 * self.scale), int(14 * self.scale)), border_radius=int(7 * self.scale))
        else:
            handle_x = box.x + int(4 * self.scale)
            pygame.draw.rect(surf, (200, 200, 200), (handle_x, box.y + int(4 * self.scale), int(14 * self.scale), int(14 * self.scale)), border_radius=int(7 * self.scale))

        # draw border
        pygame.draw.rect(surf, PANEL_BORDER, box, 2, border_radius=int(12 * self.scale))

    def handle_event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN:
            # toggle if clicked inside whole area 
            if self.rect.collidepoint(ev.pos):
                self.on = not self.on
                return True
        return False

    def set_rect(self, rect, scale):
        self.rect = pygame.Rect(rect)
        self.scale = scale


# Main App

class ProjectileApp:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("Projectile Motion")
        self.scale = self.width / BASE_W

        # fonts 
        self.create_fonts()

        # UI elements 
        self.angle_field = None
        self.speed_field = None
        self.mass_field = None
        self.height_field = None
        self.air_toggle = None
        self.launch_btn = None
        self.clear_btn = None
        self.export_btn = None

        # simulation state
        self.projectiles = []  # list of Projectile
        self.is_playing = True  # whether stepping simulation
        self.selected_index = None  # index of selected projectile for info highlight

        
        self.layout()

    def create_fonts(self):
        
        self.font = pygame.font.Font(None, max(16, int(20 * self.scale)))
        self.title_font = pygame.font.Font(None, max(24, int(40 * self.scale)))
        self.mono = pygame.font.SysFont('Consolas', max(14, int(16 * self.scale)))
        self.small = pygame.font.Font(None, max(12, int(16 * self.scale)))

    def layout(self):
       
        self.scale = self.width / BASE_W
        self.create_fonts()

       
        panel_w = int(320 * self.scale)
        panel_x = int(30 * self.scale)
        panel_y = int(80 * self.scale)
        panel_h = int(self.height - 120 * self.scale)
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        field_w = panel_w - int(40 * self.scale)
        field_h = int(42 * self.scale)
        fx = panel_x + int(20 * self.scale)
        fy = panel_y + int(20 * self.scale)

        # create text fields
        self.angle_field = TextField("Angle (°)", "45", self.font, (fx, fy + 0 * (field_h + 18 * self.scale), field_w, field_h), self.scale)
        self.speed_field = TextField("Initial Speed (m/s)", "25", self.font, (fx, fy + 1 * (field_h + 18 * self.scale), field_w, field_h), self.scale)
        self.mass_field = TextField("Mass (kg)", "1", self.font, (fx, fy + 2 * (field_h + 18 * self.scale), field_w, field_h), self.scale)
        self.height_field = TextField("Starting Height (m)", "0", self.font, (fx, fy + 3 * (field_h + 18 * self.scale), field_w, field_h), self.scale)

        # toggle
        toggley = fy + 4 * (field_h + 18 * self.scale)
        self.air_toggle = Toggle("Air Resistance", self.font, (fx, toggley, field_w, int(40 * self.scale)), on=True, scale=self.scale)

        # buttons
        btn_h = int(44 * self.scale)
        btn_w = (field_w - int(12 * self.scale)) // 2
        bx = fx
        by = toggley + int(64 * self.scale)
        self.launch_btn = Button("Launch", self.font, (bx, by, btn_w, btn_h), ACCENT, self.scale)
        self.clear_btn = Button("Clear All", self.font, (bx + btn_w + int(12 * self.scale), by, btn_w, btn_h), BAD, self.scale)

        by2 = by + btn_h + int(12 * self.scale)
        # export full width
        self.export_btn = Button("Export Trajectories (CSV)", self.font, (fx, by2, field_w, btn_h), (100, 200, 180), self.scale)

        # graph area (right)
        gx = panel_x + panel_w + int(30 * self.scale)
        gy = int(80 * self.scale)
        gw = self.width - gx - int(30 * self.scale)
        gh = self.height - gy - int(80 * self.scale)
        self.graph_rect = pygame.Rect(gx, gy, gw, gh)

    def spawn_projectile(self):
        angle = self.angle_field.get_value()
        speed = self.speed_field.get_value()
        mass = max(0.0001, self.mass_field.get_value())
        h0 = max(0.0, self.height_field.get_value())
        air = self.air_toggle.on
        p = Projectile(angle, speed, mass, h0, air_resistance=air, color=gen_color())
        self.projectiles.append(p)
        self.selected_index = len(self.projectiles) - 1

    def clear_all(self):
        self.projectiles = []
        self.selected_index = None

    def export_csv(self):
        if not self.projectiles:
            self.flash_message("No trajectories to export", BAD)
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"trajectories_{ts}.csv"
        try:
            with open(fname, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["ProjectileSim Export", f"Generated {datetime.now().isoformat()}"])
                writer.writerow([])
                # each projectile block
                for i, p in enumerate(self.projectiles, start=1):
                    writer.writerow([f"Projectile {i}", "angle_deg", math.degrees(p.angle), "speed_m_s", p.v0, "mass_kg", p.mass, "air_resistance", p.air, "start_height_m", p.y0])
                    writer.writerow(["time_s", "x_m", "y_m"])
                    for t, x, y in p.trajectory:
                        writer.writerow([f"{t:.5f}", f"{x:.5f}", f"{y:.5f}"])
                    writer.writerow([])
            self.flash_message(f"Exported to {fname}", GOOD)
        except Exception as e:
            self.flash_message(f"Export failed: {e}", BAD)

    def flash_message(self, text, color, duration=3.0):
        # simple transient message on screen (stores for a few seconds)
        self.msg_text = text
        self.msg_color = color
        self.msg_timer = duration * FPS

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif ev.type == pygame.VIDEORESIZE:
                # update screen size and re-layout
                self.width, self.height = ev.w, ev.h
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                self.layout()
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                if ev.key == pygame.K_SPACE:
                    # toggle play/pause
                    self.is_playing = not self.is_playing
            # forward to UI elements
            self.angle_field.handle_event(ev)
            self.speed_field.handle_event(ev)
            self.mass_field.handle_event(ev)
            self.height_field.handle_event(ev)
            if self.air_toggle.handle_event(ev):
                # toggled
                pass

            if self.launch_btn.handle_event(ev):
                self.spawn_projectile()
            if self.clear_btn.handle_event(ev):
                self.clear_all()
            if self.export_btn.handle_event(ev):
                self.export_csv()

            # selection: clicking on a trajectory point 
            if ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                if self.graph_rect.collidepoint((mx, my)):
                    # find nearest projectile point within some pixel radius
                    nearest = None
                    nr_dist = 9999
                    sel_idx = None
                    for idx, p in enumerate(self.projectiles):
                        if not p.trajectory: continue
                        for (t, x, y) in p.trajectory:
                            sx, sy = self.world_to_screen(x, y)
                            d = math.hypot(sx - mx, sy - my)
                            if d < nr_dist and d < 12 * self.scale:
                                nr_dist = d
                                nearest = p
                                sel_idx = idx
                    if sel_idx is not None:
                        self.selected_index = sel_idx

    def update(self):
        # advance simulation for each projectile if playing
        if self.is_playing:
            for p in self.projectiles:
                if not p.landed:
                    p.step()

        # decrease message timer
        if hasattr(self, 'msg_timer') and self.msg_timer > 0:
            self.msg_timer -= 1
            if self.msg_timer <= 0:
                self.msg_text = ""
                self.msg_color = None

    # conversion from physics meters to screen pixels (world origin at bottom-left of graph area)
    def world_to_screen(self, x_m, y_m):
        gx, gy, gw, gh = self.graph_rect
        # mapping: calculate visible extents automatically based on projectiles
        # find max extents across all trajectories for scaling (with minimum defaults)
        max_x = 10.0
        max_y = 5.0
        for p in self.projectiles:
            for (_, x, y) in p.trajectory:
                if x > max_x: max_x = x
                if y > max_y: max_y = y
        # add padding
        max_x *= 1.2
        max_y *= 1.2
        # avoid zero
        max_x = max(max_x, 1e-3)
        max_y = max(max_y, 1e-3)

        # horizontal: left = graph left, right = graph left + gw
        sx = gx + (x_m / max_x) * gw
        # vertical: bottom = gy + gh, top = gy
        sy = gy + gh - (y_m / max_y) * gh
        return int(sx), int(sy)

    def draw(self):
        # background
        self.screen.fill(BG)

        # title
        title = self.title_font.render("Projectile Motion", True, TEXT)
        self.screen.blit(title, (int(30 * self.scale), int(20 * self.scale)))

        # left panel
        pygame.draw.rect(self.screen, PANEL, self.panel_rect, border_radius=int(10 * self.scale))
        pygame.draw.rect(self.screen, PANEL_BORDER, self.panel_rect, 2, border_radius=int(10 * self.scale))

        # draw UI elements
        for widget in (self.angle_field, self.speed_field, self.mass_field, self.height_field):
            widget.draw(self.screen)
        self.air_toggle.draw(self.screen)
        self.launch_btn.draw(self.screen)
        self.clear_btn.draw(self.screen)
        self.export_btn.draw(self.screen)

        # graph panel
        pygame.draw.rect(self.screen, (12, 14, 18), self.graph_rect, border_radius=int(8 * self.scale))
        pygame.draw.rect(self.screen, (40, 44, 50), self.graph_rect, 2, border_radius=int(8 * self.scale))

        # draw grid lines and axes labels
        gx, gy, gw, gh = self.graph_rect
        # determine extents again to draw ticks
        max_x = 10.0
        max_y = 5.0
        for p in self.projectiles:
            for (_, x, y) in p.trajectory:
                if x > max_x: max_x = x
                if y > max_y: max_y = y
        max_x *= 1.2
        max_y *= 1.2
        max_x = max(max_x, 1e-3)
        max_y = max(max_y, 1e-3)

        # draw a modest grid 5x5
        nx = 5
        ny = 5
        for i in range(nx + 1):
            x = gx + int(i * gw / nx)
            pygame.draw.line(self.screen, GRID, (x, gy), (x, gy + gh), 1)
            # label
            val = max_x * (i / nx)
            lbl = self.small.render(f"{val:.1f} m", True, (160, 170, 180))
            self.screen.blit(lbl, (x - lbl.get_width() // 2, gy + gh + int(6 * self.scale)))

        for j in range(ny + 1):
            y = gy + int(j * gh / ny)
            pygame.draw.line(self.screen, GRID, (gx, y), (gx + gw, y), 1)
            val = max_y * (1 - j / ny)
            lbl = self.small.render(f"{val:.1f} m", True, (160, 170, 180))
            self.screen.blit(lbl, (gx - int(8 * self.scale) - lbl.get_width(), y - lbl.get_height() // 2))

        # draw projectiles trajectories
        for idx, p in enumerate(self.projectiles):
            # build scaled points
            pts = []
            for (t, x, y) in p.trajectory:
                sx, sy = self.world_to_screen(x, y)
                pts.append((sx, sy))
            if len(pts) >= 2:
                # line
                pygame.draw.lines(self.screen, p.color, False, pts, max(1, int(2 * self.scale)))
                # draw last point if flying
                if not p.landed:
                    pygame.draw.circle(self.screen, p.color, pts[-1], max(3, int(5 * self.scale)))
                else:
                    # landed marker
                    pygame.draw.circle(self.screen, p.color, pts[-1], max(3, int(5 * self.scale)), 2)

        # right-side info panel inside graph area: show measurements for selected projectile or summary
        info_x = gx + int(8 * self.scale)
        info_y = gy + int(8 * self.scale)
        info_w = int(320 * self.scale)
        info_h = int(160 * self.scale)
        info_rect = pygame.Rect(info_x, info_y, info_w, info_h)
        pygame.draw.rect(self.screen, (18, 20, 25, 180), info_rect, border_radius=int(8 * self.scale))
        pygame.draw.rect(self.screen, (60, 66, 78), info_rect, 1, border_radius=int(8 * self.scale))

        header = self.font.render("Measurements", True, TEXT)
        self.screen.blit(header, (info_rect.x + int(10 * self.scale), info_rect.y + int(8 * self.scale)))

        # display metrics
        sy = info_rect.y + int(36 * self.scale)
        if self.selected_index is not None and 0 <= self.selected_index < len(self.projectiles):
            p = self.projectiles[self.selected_index]
            lines = [
                f"Projectile #{self.selected_index + 1}",
                f"Angle: {math.degrees(p.angle):.1f}°",
                f"Speed: {p.v0:.2f} m/s",
                f"Mass: {p.mass:.3f} kg",
                f"Air resist.: {'ON' if p.air else 'OFF'}",
                f"Max height: {p.max_height:.3f} m",
                f"Flight time: {p.flight_time:.3f} s" if p.landed else f"Flight time: —",
                f"Range: {p.range:.3f} m" if p.landed else f"Range: —",
                f"Final speed: {p.final_speed:.3f} m/s" if p.landed else f"Final speed: —",
            ]
        else:
            lines = [
                f"Projectiles: {len(self.projectiles)}",
                "Click a trajectory to see details.",
                "Press SPACE to pause/play.",
                "F11 toggles fullscreen.",
            ]

        for ln in lines:
            txt = self.small.render(ln, True, (200, 210, 220))
            self.screen.blit(txt, (info_rect.x + int(10 * self.scale), sy))
            sy += int(18 * self.scale)

        # transient message
        if hasattr(self, 'msg_timer') and getattr(self, 'msg_timer', 0) > 0:
            mt = self.font.render(self.msg_text, True, self.msg_color)
            mx = int(self.width / 2 - mt.get_width() / 2)
            my = int(self.height - 40 * self.scale)
            # small background
            bg_rect = pygame.Rect(mx - 8, my - 6, mt.get_width() + 16, mt.get_height() + 12)
            pygame.draw.rect(self.screen, (16, 18, 22), bg_rect, border_radius=int(6 * self.scale))
            self.screen.blit(mt, (mx, my))

        # footer hint
        footer = self.small.render("Launch multiple projectiles, toggle air resistance, export CSV", True, (150, 160, 170))
        self.screen.blit(footer, (int(30 * self.scale), int(self.height - 34 * self.scale)))

        pygame.display.flip()

    def run(self):
        # initial message blanks
        self.msg_text = ""
        self.msg_timer = 0
        while True:
            CLOCK.tick(FPS)
            self.handle_events()
            self.update()
            self.draw()

# -----------------------
# Run the app
# -----------------------
if __name__ == "__main__":
    app = ProjectileApp(WIDTH, HEIGHT)
    app.run()
