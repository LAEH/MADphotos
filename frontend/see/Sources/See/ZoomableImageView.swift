import SwiftUI
import AppKit

struct ZoomableImageView: View {
    @EnvironmentObject var store: PhotoStore
    let photo: PhotoItem

    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var displayImage: NSImage?
    @State private var fullImage: NSImage?
    @State private var imageOpacity: Double = 0
    @State private var currentTier: String = "thumb"

    private var currentImage: NSImage? {
        fullImage ?? displayImage ?? store.loadThumbnail(for: photo)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.black

                if let img = currentImage {
                    Image(nsImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .scaleEffect(scale)
                        .offset(offset)
                        .opacity(imageOpacity)
                        .gesture(magnifyGesture.simultaneously(with: dragGesture))
                        .onTapGesture(count: 2) { toggleZoom(in: geo.size) }
                }

                // Zoom indicator
                if scale > 1.05 {
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            Text("\(Int(scale * 100))%")
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundColor(.white.opacity(0.9))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Capsule().fill(Color.black.opacity(0.5)))
                        }
                        .padding(12)
                    }
                    .transition(.opacity)
                    .allowsHitTesting(false)
                }
            }
            .clipped()
        }
        .task(id: photo.id) {
            resetState()
            loadDisplayTier()
        }
        .onChange(of: store.showEnhanced) { _, _ in
            loadDisplayTier()
        }
        .onChange(of: photo.displayVariant) { _, _ in
            displayImage = nil
            fullImage = nil
            loadDisplayTier()
        }
    }

    // MARK: - Gestures

    private var magnifyGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                let newScale = lastScale * value.magnification
                scale = min(max(newScale, 0.5), 10.0)
            }
            .onEnded { value in
                let newScale = lastScale * value.magnification
                scale = min(max(newScale, 1.0), 10.0)

                if scale <= 1.05 {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        scale = 1.0
                        offset = .zero
                    }
                    lastScale = 1.0
                    lastOffset = .zero
                } else {
                    lastScale = scale
                    if scale > 2.0 { loadFullTier() }
                }
            }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                guard scale > 1.0 else { return }
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
            }
            .onEnded { value in
                guard scale > 1.0 else { return }
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
                clampOffset()
                lastOffset = offset
            }
    }

    // MARK: - Zoom toggle

    private func toggleZoom(in size: CGSize) {
        if scale > 1.05 {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                scale = 1.0
                offset = .zero
            }
            lastScale = 1.0
            lastOffset = .zero
        } else {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                scale = 2.5
            }
            lastScale = 2.5
            loadFullTier()
        }
    }

    // MARK: - Offset clamping

    private func clampOffset() {
        let maxX = max(0, (scale - 1) * 200)
        let maxY = max(0, (scale - 1) * 150)
        offset = CGSize(
            width: min(max(offset.width, -maxX), maxX),
            height: min(max(offset.height, -maxY), maxY)
        )
    }

    // MARK: - Tier loading

    private func resetState() {
        scale = 1.0
        lastScale = 1.0
        offset = .zero
        lastOffset = .zero
        displayImage = nil
        fullImage = nil
        currentTier = "thumb"

        // Show thumb instantly if cached
        if store.loadThumbnail(for: photo) != nil {
            imageOpacity = 1.0
        } else {
            imageOpacity = 0
        }
    }

    private func loadDisplayTier() {
        let photoId = photo.id

        // Check display cache first
        if let cached = store.loadDisplayImage(for: photo) {
            displayImage = cached
            currentTier = "display"
            withAnimation(.easeIn(duration: 0.2)) { imageOpacity = 1.0 }
            return
        }

        let path = store.currentImagePath(for: photo)
        Task.detached(priority: .userInitiated) {
            guard let img = NSImage(contentsOfFile: path) else { return }
            await MainActor.run {
                guard self.photo.id == photoId else { return }
                self.store.cacheDisplayImage(img, for: self.photo)
                self.displayImage = img
                self.currentTier = "display"
                withAnimation(.easeIn(duration: 0.3)) { self.imageOpacity = 1.0 }
            }
        }
    }

    private func loadFullTier() {
        guard currentTier != "full" else { return }
        let photoId = photo.id
        let path = store.fullImagePath(for: photo)

        Task.detached(priority: .userInitiated) {
            guard FileManager.default.fileExists(atPath: path),
                  let img = NSImage(contentsOfFile: path) else { return }
            await MainActor.run {
                guard self.photo.id == photoId else { return }
                self.fullImage = img
                self.currentTier = "full"
            }
        }
    }
}
