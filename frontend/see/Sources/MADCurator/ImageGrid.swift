import SwiftUI

struct ImageGrid: View {
    @EnvironmentObject var store: PhotoStore
    private let columns = [GridItem(.adaptive(minimum: 160, maximum: 240), spacing: 4)]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVGrid(columns: columns, spacing: 4) {
                    ForEach(store.filteredPhotos) { photo in
                        ThumbnailCell(photo: photo)
                            .id(photo.id)
                            .onTapGesture { store.selectPhoto(photo) }
                            .contextMenu {
                                Button {
                                    store.curate(photo, status: "kept")
                                } label: {
                                    Label("Keep", systemImage: "checkmark.circle.fill")
                                }
                                Button {
                                    store.curate(photo, status: "rejected")
                                } label: {
                                    Label("Reject", systemImage: "xmark.circle.fill")
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
                .padding(4)
                .animation(.easeInOut(duration: 0.25), value: store.filteredPhotos.count)
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

    private var isSelected: Bool { store.selectedPhoto?.id == photo.id }
    private var isRejected: Bool { photo.curatedStatus == "rejected" }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            // Thumbnail image
            if let nsImage = store.loadThumbnail(for: photo) {
                Image(nsImage: nsImage)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                Rectangle()
                    .fill(Color.gray.opacity(0.08))
                    .aspectRatio(photo.aspectRatio, contentMode: .fit)
                    .overlay(
                        Image(systemName: "photo")
                            .font(.title2)
                            .foregroundColor(.gray.opacity(0.2))
                    )
            }

            // Status indicators
            HStack(spacing: 3) {
                if photo.curatedStatus == "kept" {
                    Circle().fill(.green).frame(width: 6, height: 6)
                } else if isRejected {
                    Circle().fill(.red).frame(width: 6, height: 6)
                }

                if !photo.isAnalyzed {
                    Image(systemName: "clock")
                        .font(.system(size: 8))
                        .foregroundColor(.white.opacity(0.7))
                }

                // Location pin indicator
                if photo.hasLocation {
                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 8))
                        .foregroundColor(.white.opacity(0.8))
                }
            }
            .padding(4)

            // Aesthetic score indicator (top-right)
            if let stars = photo.aestheticStars {
                VStack {
                    HStack {
                        Spacer()
                        Text(String(format: "%.1f", stars))
                            .font(.system(.caption2, design: .monospaced))
                            .fontWeight(.bold)
                            .foregroundColor(.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(aestheticColor(stars).opacity(0.8))
                            )
                            .padding(4)
                    }
                    Spacer()
                }
            }
        }
        // Selection ring
        .overlay(
            RoundedRectangle(cornerRadius: 3)
                .strokeBorder(Color.accentColor, lineWidth: 2.5)
                .opacity(isSelected ? 1 : 0)
        )
        .clipShape(RoundedRectangle(cornerRadius: 3))
        // Rejected: fade + desaturate
        .opacity(isRejected ? 0.3 : 1.0)
        .saturation(isRejected ? 0.3 : 1.0)
        // Hover effect
        .scaleEffect(isHovered && !isSelected ? 1.02 : 1.0)
        .shadow(color: .black.opacity(isHovered && !isSelected ? 0.15 : 0), radius: 4, y: 2)
        .animation(.spring(response: 0.25, dampingFraction: 0.7), value: isHovered)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)
        .onHover { hovering in isHovered = hovering }
    }

    private func aestheticColor(_ stars: Double) -> Color {
        if stars >= 4.0 { return .green }
        if stars >= 3.0 { return .orange }
        return .red
    }
}
