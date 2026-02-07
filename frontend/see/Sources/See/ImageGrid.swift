import SwiftUI

struct ImageGrid: View {
    @EnvironmentObject var store: PhotoStore
    private let columns = [GridItem(.adaptive(minimum: 150, maximum: 220), spacing: 2)]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVGrid(columns: columns, spacing: 2) {
                    ForEach(store.filteredPhotos) { photo in
                        ThumbnailCell(photo: photo)
                            .id(photo.id)
                            .onTapGesture {
                                if store.isSelectMode {
                                    store.togglePhotoSelection(photo)
                                } else {
                                    store.selectPhoto(photo)
                                }
                            }
                            .contextMenu {
                                Button {
                                    store.curate(photo, status: "kept")
                                } label: {
                                    Label("Pick", systemImage: "checkmark.circle.fill")
                                }
                                Button {
                                    store.curate(photo, status: "rejected")
                                } label: {
                                    Label("Reject", systemImage: "xmark.circle.fill")
                                }
                                Button {
                                    store.curate(photo, status: "pending")
                                } label: {
                                    Label("Unflag", systemImage: "circle")
                                }
                                Divider()
                                Button {
                                    NSPasteboard.general.clearContents()
                                    NSPasteboard.general.setString(photo.id, forType: .string)
                                } label: {
                                    Label("Copy UUID", systemImage: "doc.on.doc")
                                }
                            }
                    }
                }
                .padding(2)
            }
            .onChange(of: store.selectedPhoto) { _, newVal in
                if let photo = newVal {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(photo.id, anchor: .center)
                    }
                }
            }
        }
    }
}

struct ThumbnailCell: View {
    @EnvironmentObject var store: PhotoStore
    let photo: PhotoItem
    @State private var isHovered = false
    @State private var thumb: NSImage?

    private var isSelected: Bool { store.selectedPhoto?.id == photo.id }
    private var isRejected: Bool { photo.curatedStatus == "rejected" }
    private var isKept: Bool { photo.curatedStatus == "kept" }
    private var isMultiSelected: Bool { store.selectedPhotos.contains(photo.id) }

    var body: some View {
        ZStack {
            // Thumbnail image
            if let nsImage = thumb {
                if store.squareCrop {
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                        .aspectRatio(1, contentMode: .fit)
                        .clipped()
                } else {
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                }
            } else {
                Rectangle()
                    .fill(Color.gray.opacity(0.08))
                    .aspectRatio(1, contentMode: .fit)
            }

            // Status badge (bottom-left)
            if isKept || isRejected || photo.hasLocation {
                VStack {
                    Spacer()
                    HStack(spacing: 3) {
                        if isKept {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.green)
                                .shadow(color: .black.opacity(0.5), radius: 2)
                        } else if isRejected {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.red)
                                .shadow(color: .black.opacity(0.5), radius: 2)
                        }

                        if photo.hasLocation {
                            Image(systemName: "mappin.circle.fill")
                                .font(.system(size: 9))
                                .foregroundColor(.white.opacity(0.8))
                                .shadow(color: .black.opacity(0.5), radius: 1)
                        }
                        Spacer()
                    }
                    .padding(4)
                }
            }

            // Multi-select checkmark (top-right)
            if store.isSelectMode {
                VStack {
                    HStack {
                        Spacer()
                        ZStack {
                            Circle()
                                .fill(isMultiSelected ? Color.accentColor : Color.black.opacity(0.4))
                                .frame(width: 20, height: 20)
                            Circle()
                                .strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5)
                                .frame(width: 20, height: 20)
                            if isMultiSelected {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.white)
                            }
                        }
                        .shadow(color: .black.opacity(0.3), radius: 2)
                        .padding(5)
                        .contentShape(Circle())
                        .onTapGesture {
                            store.togglePhotoSelection(photo)
                        }
                    }
                    Spacer()
                }
                .allowsHitTesting(true)
            }
        }
        // Selection ring
        .overlay(
            RoundedRectangle(cornerRadius: 2)
                .strokeBorder(Color.accentColor, lineWidth: 3)
                .opacity(isSelected || isMultiSelected ? 1 : 0)
        )
        .clipShape(RoundedRectangle(cornerRadius: 2))
        // Rejected: fade + desaturate
        .opacity(isRejected ? 0.35 : 1.0)
        .saturation(isRejected ? 0.3 : 1.0)
        // Hover
        .brightness(isHovered && !isSelected ? 0.06 : 0)
        .scaleEffect(isHovered && !isSelected ? 1.02 : 1.0)
        .animation(.easeOut(duration: 0.12), value: isHovered)
        .onHover { hovering in isHovered = hovering }
        // Async thumb load
        .task(id: photo.id) {
            if let cached = store.loadThumbnail(for: photo) {
                thumb = cached
            } else {
                let path = store.thumbnailPath(for: photo)
                let loaded = await Task.detached {
                    NSImage(contentsOfFile: path)
                }.value
                if let img = loaded {
                    store.cacheThumbnail(img, for: photo)
                    thumb = img
                }
            }
        }
    }
}
