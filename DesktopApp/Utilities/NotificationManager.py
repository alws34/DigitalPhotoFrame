import tkinter as tk


class NotificationManager:
    def __init__(self, root):
        self.root = root
        self.notifications = []
        self.remove_time = 5000  # Time in milliseconds before a notification is removed

    def create_notification(self, message, type_="info"):
        colors = {"info": "#0000FF", "success": "#008000", "error": "#FF0000"}
        bg_color = colors.get(type_, "#000000")

        width = 400
        height = 60
        x_pos = self.root.winfo_screenwidth() - width - 20
        y_pos = 20 + len(self.notifications) * (height + 10)

        notification = tk.Toplevel(self.root)
        notification.overrideredirect(True)
        notification.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
        notification.configure(bg=bg_color)
        notification.resizable(False, False)
        notification.attributes("-topmost", True)
        notification.attributes("-alpha", 0.0)  # Start fully transparent

        label = tk.Label(
            notification,
            text=message,
            bg=bg_color,
            fg="white",
            font=("Helvetica", 14),
            padx=10,
            pady=5,
            wraplength=380,
        )
        label.pack(fill="both", expand=True)

        self.notifications.append(notification)
        self.fade_in(notification, x_pos, y_pos)

    def fade_in(self, notification, x_pos, target_y, step=5, alpha_step=0.05):
        """
        Animate the fade-in effect by sliding the notification into position and increasing transparency.

        Args:
            notification (Toplevel): The notification window.
            x_pos (int): The horizontal position of the notification.
            target_y (int): The final vertical position.
            step (int): Vertical movement per frame.
            alpha_step (float): Transparency increment per frame.
        """
        try:
            # Get current geometry
            geometry = notification.geometry()
            _, _, _, current_y = map(int, geometry.replace("x", "+").split("+"))

            # Move downward
            current_y += step
            if current_y > target_y:
                current_y = target_y  # Clamp to target position

            # Update position
            notification.geometry(f"{400}x{60}+{x_pos}+{current_y}")

            # Incrementally increase transparency
            alpha = notification.attributes("-alpha")
            new_alpha = min(alpha + alpha_step, 0.9)  # Max alpha = 0.9
            notification.attributes("-alpha", new_alpha)

            # Continue animation until fully visible
            if current_y < target_y or alpha < 0.9:
                self.root.after(16, lambda: self.fade_in(notification, x_pos, target_y, step, alpha_step))
            else:
                # Schedule removal after fade-in completes
                self.root.after(self.remove_time, lambda: self.swipe_right_effect(notification))
        except Exception as e:
            print(f"Error during fade-in effect: {e}")

    def swipe_right_effect(self, notification, step=20):
        """
        Remove the notification with a swipe-right effect.

        Args:
            notification (Toplevel): The notification to remove.
            step (int): Number of pixels to move per frame.
        """
        try:
            # Get current geometry
            geometry = notification.geometry()
            width, height, x_pos, y_pos = map(int, geometry.replace("x", "+").split("+"))

            # Move the notification to the right
            x_pos += step
            notification.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

            # If the notification is fully off-screen, destroy it
            if x_pos > self.root.winfo_screenwidth():
                self.remove_notification(notification)
            else:
                # Continue the animation
                self.root.after(16, lambda: self.swipe_right_effect(notification, step))
        except Exception as e:
            print(f"Error during swipe-right effect: {e}")

    def remove_notification(self, notification):
        """Remove the notification."""
        if notification in self.notifications:
            self.notifications.remove(notification)
            notification.destroy()

    def remove_all_notifications(self):
        """Remove all notifications."""
        for notification in self.notifications:
            self.remove_notification(notification)
