package com.photoframe;

import com.defano.jsegue.*;
import com.defano.jsegue.renderers.AlphaDissolveEffect;
import com.defano.jsegue.renderers.BarnDoorCloseEffect;
import com.defano.jsegue.renderers.BarnDoorOpenEffect;
import com.defano.jsegue.renderers.BlindsEffect;
import com.defano.jsegue.renderers.CheckerboardEffect;
import com.defano.jsegue.renderers.IrisCloseEffect;
import com.defano.jsegue.renderers.IrisOpenEffect;
import com.defano.jsegue.renderers.PixelDissolveEffect;
import com.defano.jsegue.renderers.ScrollDownEffect;
import com.defano.jsegue.renderers.ScrollLeftEffect;
import com.defano.jsegue.renderers.ScrollRightEffect;
import com.defano.jsegue.renderers.ScrollUpEffect;
import com.defano.jsegue.renderers.ShrinkToBottomEffect;
import com.defano.jsegue.renderers.ShrinkToCenterEffect;
import com.defano.jsegue.renderers.ShrinkToTopEffect;
import com.defano.jsegue.renderers.StretchFromBottomEffect;
import com.defano.jsegue.renderers.StretchFromCenterEffect;
import com.defano.jsegue.renderers.StretchFromTopEffect;
import com.defano.jsegue.renderers.WipeDownEffect;
import com.defano.jsegue.renderers.WipeLeftEffect;
import com.defano.jsegue.renderers.WipeRightEffect;
import com.defano.jsegue.renderers.WipeUpEffect;
import com.defano.jsegue.renderers.ZoomInEffect;
import com.defano.jsegue.renderers.ZoomOutEffect;

import java.awt.*;
import java.awt.event.*;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import javax.swing.*;
import java.util.Random;

public class PhotoFrame extends JFrame implements SegueAnimationObserver {

    private static final long DEFAULT_ANIMATION_DURATION = 5000; // 5 seconds
    private static final int DEFAULT_SLEEP_DURATION = 30000; // 30 seconds
    private static final int DEFAULT_MAX_FPS = 30;
    private static final int DEFAULT_MAX_ANIMATIONS = 24; // this is all the animation segue supports.
    private JPanel photoPanel;
    private JLabel photoLabel;
    private List<BufferedImage> photos;
    private int currentPhotoIndex;
    private AnimatedSegue currentSegue;
    private int screenWidth;
    private int screenHeight;

    public PhotoFrame() {
        super("Photo Frame");
        setExtendedState(JFrame.MAXIMIZED_BOTH);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        // Create and add the photo panel
        photoPanel = new JPanel();
        photoPanel.setLayout(new BorderLayout());
        photoLabel = new JLabel();
        photoLabel.setHorizontalAlignment(SwingConstants.CENTER);
        photoPanel.add(photoLabel, BorderLayout.CENTER);
        add(photoPanel, BorderLayout.CENTER); // Add panel to frame

        // Add window listener to handle fullscreen mode
        addWindowListener(new WindowAdapter() {
            @Override
            public void windowOpened(WindowEvent e) {
                setUndecorated(true); // Remove window decorations
            }
        });

        setScreenSize();
        photos = LoadPhotos();
        if (photos.isEmpty())
            return;

        currentPhotoIndex = 0;
        startPhotoLoop();
    }

    // region Animations
    public void setSegue(BufferedImage sourceImage, BufferedImage destinationImage) {
        switch (getRandInt(DEFAULT_MAX_ANIMATIONS)) {
            case 1:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        PixelDissolveEffect.class);
                break;
            case 2:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        AlphaDissolveEffect.class);
                break;
            case 3:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        CheckerboardEffect.class);
                break;
            case 4:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BlindsEffect.class);
                break;
            case 5:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollLeftEffect.class);
                break;
            case 6:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollRightEffect.class);
                break;
            case 7:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollUpEffect.class);
                break;
            case 8:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollDownEffect.class);
                break;
            case 9:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeLeftEffect.class);
                break;
            case 10:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeRightEffect.class);
                break;
            case 11:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeUpEffect.class);
                break;
            case 12:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        WipeDownEffect.class);
                break;
            case 13:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ZoomOutEffect.class);
                break;
            case 14:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ZoomInEffect.class);
                break;
            case 15:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        IrisOpenEffect.class);
                break;
            case 16:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        IrisCloseEffect.class);
                break;
            case 17:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BarnDoorOpenEffect.class);
                break;
            case 18:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        BarnDoorCloseEffect.class);
                break;
            case 19:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToBottomEffect.class);
                break;
            case 20:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToTopEffect.class);
                break;
            case 21:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ShrinkToCenterEffect.class);
                break;
            case 22:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromBottomEffect.class);
                break;
            case 23:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromTopEffect.class);
                break;
            case 24:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        StretchFromCenterEffect.class);
                break;
            default:
                currentSegue = buildSegue(sourceImage, destinationImage,
                        ScrollLeftEffect.class);
                break;
        }
    }

    public AnimatedSegue buildSegue(BufferedImage source, BufferedImage destination,
            Class<? extends AnimatedSegue> effectClass) {
        return SegueBuilder.of(effectClass)
                .withSource(source)
                .withDestination(destination)
                .withDuration((int) DEFAULT_ANIMATION_DURATION, TimeUnit.MILLISECONDS)
                .withMaxFramesPerSecond(DEFAULT_MAX_FPS)
                .withAnimationObserver(this)
                .withCompletionObserver(null)
                .build();
    }
    // endregion Animations

    private void setScreenSize() {
        Dimension screenSize = Toolkit.getDefaultToolkit().getScreenSize();

        // Get the screen width and height
        screenWidth = (int) screenSize.getWidth();
        screenHeight = (int) screenSize.getHeight();

        // Set the window Size
        setSize(screenSize.width, screenSize.height);
    }

    private void startPhotoLoop() {
        new Thread(() -> {
            while (true) {
                if (currentPhotoIndex >= photos.size()) {
                    currentPhotoIndex = 0; // Wrap around
                }

                // Resize images to screen size (assuming we know the screen dimensions)
                BufferedImage resizedSourceImage = resizeImage(photos.get(currentPhotoIndex), screenWidth,
                        screenHeight);
                BufferedImage resizedDestinationImage = resizeImage(photos.get((currentPhotoIndex + 1) % photos.size()),
                        screenWidth, screenHeight);

                setSegue(resizedSourceImage, resizedDestinationImage);
                currentSegue.start();

                currentPhotoIndex++;

                try {
                    // Wait for the animation to finish + wait for the next anomation
                    Thread.sleep(DEFAULT_SLEEP_DURATION + DEFAULT_ANIMATION_DURATION);
                } catch (InterruptedException e) {
                    // Handle interruptions gracefully
                }
            }
        }).start();
    }

    private List<BufferedImage> LoadPhotos() {
        photos = new ArrayList<>();
        try {
            File[] imageFiles = new File("resources")
                    .listFiles(file -> file.isFile() &&
                            (file.getName().toLowerCase().endsWith(".jpg") ||
                                    file.getName().toLowerCase().endsWith(".png") ||
                                    file.getName().toLowerCase().endsWith(".jpeg") ||
                                    file.getName().toLowerCase().endsWith(".heic") ||
                                    file.getName().toLowerCase().endsWith(".heif")));
            if (imageFiles != null) {
                for (File imageFile : imageFiles) {
                    try {
                        photos.add(ImageIO.read(imageFile));
                    } catch (Exception e) {
                        continue;
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        return photos;
    }

    private BufferedImage resizeImage(BufferedImage image, int width, int height) {
        BufferedImage resizedImage = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = resizedImage.createGraphics();
        g2d.drawImage(image.getScaledInstance(width, height, Image.SCALE_SMOOTH), 0, 0, null);
        g2d.dispose();
        return resizedImage;
    }

    @Override
    public void onFrameRendered(AnimatedSegue segue, BufferedImage image) {
        photoLabel.setIcon(new ImageIcon(image));
    }

    public static int getRandInt(int max) {
        Random random = new Random();
        return random.nextInt(max) + 1;
    }
}
