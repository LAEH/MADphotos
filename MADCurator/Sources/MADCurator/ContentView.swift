import SwiftUI

struct ContentView: View {
    @EnvironmentObject var store: PhotoStore

    var body: some View {
        NavigationSplitView {
            FilterSidebar()
        } content: {
            VStack(spacing: 0) {
                if store.filters.isActive {
                    QueryBar()
                }
                ImageGrid()
            }
            .frame(minWidth: 500)
        } detail: {
            if store.isFullscreen, let photo = store.selectedPhoto {
                // Fullscreen preview — just the image, black background
                ZStack {
                    Color.black.ignoresSafeArea()
                    if let nsImage = NSImage(contentsOfFile: store.currentImagePath(for: photo)) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
                .onTapGesture { store.toggleFullscreen() }
            } else if let photo = store.selectedPhoto {
                if store.showInfoPanel {
                    DetailView(photo: photo)
                        .frame(minWidth: 320)
                        .id(photo.id)
                } else {
                    // Image only, no metadata
                    VStack(spacing: 0) {
                        if let nsImage = NSImage(contentsOfFile: store.currentImagePath(for: photo)) {
                            Image(nsImage: nsImage)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxWidth: .infinity)
                                .background(Color.black)
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .id(photo.id)
                }
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "camera.viewfinder")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary.opacity(0.3))
                    Text("Select a photograph")
                        .font(.system(.body, design: .monospaced))
                        .fontWeight(.light)
                        .foregroundColor(.secondary.opacity(0.5))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationSplitViewStyle(.balanced)
        .toolbar {
            ToolbarItem(placement: .status) {
                CurationToolbar()
            }
        }
        .onAppear { store.load() }
        .onKeyPress(.escape) {
            if store.isFullscreen {
                store.isFullscreen = false
                return .handled
            }
            store.selectedPhoto = nil
            store.selectedIndex = -1
            return .handled
        }
        .onKeyPress(.space) {
            guard store.selectedPhoto != nil else { return .ignored }
            store.toggleFullscreen()
            return .handled
        }
        .onKeyPress("e") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.toggleEnhanced()
            return .handled
        }
        .onKeyPress("i") {
            store.toggleInfoPanel()
            return .handled
        }
        .onKeyPress("y") {
            guard let photo = store.selectedPhoto,
                  photo.locationSource == "propagated",
                  !photo.locationAccepted else { return .ignored }
            store.acceptLocation(for: photo)
            return .handled
        }
        .onKeyPress("n") {
            guard let photo = store.selectedPhoto,
                  photo.locationSource == "propagated",
                  !photo.locationAccepted else { return .ignored }
            store.rejectLocation(for: photo)
            return .handled
        }
    }
}

// MARK: - Query Bar

struct QueryBar: View {
    @EnvironmentObject var store: PhotoStore

    var body: some View {
        HStack(spacing: 0) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(Array(store.chipGroups.enumerated()), id: \.element.id) { idx, group in
                        // Intersection separator between dimension groups
                        if idx > 0 {
                            Text("\u{2229}")
                                .font(.system(size: 9, weight: .medium, design: .monospaced))
                                .foregroundColor(.secondary.opacity(0.4))
                                .padding(.horizontal, 3)
                                .padding(.vertical, 2)
                                .background(
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(Color.primary.opacity(0.04))
                                )
                        }
                        // Chips within a group (union by default)
                        ForEach(Array(group.chips.enumerated()), id: \.element.id) { chipIdx, chip in
                            if chipIdx > 0 {
                                Text(group.mode == .union ? "\u{222A}" : "\u{2229}")
                                    .font(.system(size: 7, design: .monospaced))
                                    .foregroundColor(.secondary.opacity(0.3))
                                    .padding(.horizontal, 2)
                                    .padding(.vertical, 1)
                                    .background(
                                        RoundedRectangle(cornerRadius: 2)
                                            .fill(Color.primary.opacity(0.03))
                                    )
                            }
                            Button(action: { store.removeChip(chip.id) }) {
                                HStack(spacing: 3) {
                                    Text(chip.label)
                                    Image(systemName: "xmark")
                                        .font(.system(size: 7, weight: .bold))
                                }
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundColor(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.accentColor.opacity(0.85)))
                                .shadow(color: Color.accentColor.opacity(0.2), radius: 2, y: 1)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.horizontal, 10)
            }

            Spacer()

            Text("\(store.filteredPhotos.count)")
                .font(.system(.caption, design: .monospaced))
                .fontWeight(.medium)
                .foregroundColor(.secondary)
                .padding(.horizontal, 8)

            Button(action: store.clearFilters) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(.caption))
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .buttonStyle(.plain)
            .padding(.trailing, 10)
        }
        .frame(height: 30)
        .background(Color(nsColor: .controlBackgroundColor).opacity(0.5))
    }
}

// MARK: - Toolbar

struct CurationToolbar: View {
    @EnvironmentObject var store: PhotoStore

    var body: some View {
        let c = store.curationCounts
        HStack(spacing: 12) {
            Label("\(store.filteredPhotos.count)", systemImage: "photo.stack")
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.secondary)

            Divider().frame(height: 16)

            HStack(spacing: 4) {
                Circle().fill(.green.opacity(0.7)).frame(width: 8, height: 8)
                Text("\(c.kept)")
                    .font(.system(.caption, design: .monospaced))
            }
            HStack(spacing: 4) {
                Circle().fill(.red.opacity(0.7)).frame(width: 8, height: 8)
                Text("\(c.rejected)")
                    .font(.system(.caption, design: .monospaced))
            }
            HStack(spacing: 4) {
                Circle().fill(.gray.opacity(0.4)).frame(width: 8, height: 8)
                Text("\(c.pending)")
                    .font(.system(.caption, design: .monospaced))
            }

            Divider().frame(height: 16)

            GeometryReader { geo in
                let total = max(c.total, 1)
                let reviewed = c.kept + c.rejected
                let pct = CGFloat(reviewed) / CGFloat(total)
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.gray.opacity(0.15))
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.primary.opacity(0.6))
                        .frame(width: geo.size.width * pct)
                }
            }
            .frame(width: 80, height: 6)

            Text("\(Int(Double(c.kept + c.rejected) / Double(max(c.total, 1)) * 100))%")
                .font(.system(.caption2, design: .monospaced))
                .foregroundColor(.secondary)
        }
    }
}
