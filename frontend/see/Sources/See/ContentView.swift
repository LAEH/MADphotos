import SwiftUI

struct ContentView: View {
    @EnvironmentObject var store: PhotoStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        NavigationSplitView {
            FilterSidebar()
                .navigationSplitViewColumnWidth(min: 160, ideal: 210, max: 300)
        } detail: {
            ZStack {
                VStack(spacing: 0) {
                    GridToolbar()
                    if store.filters.isActive {
                        QueryBar()
                    }
                    ImageGrid()
                }

                if store.isLoading {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(1.2)
                        Text("Loading collection...")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .toolbar { ToolbarItem(placement: .automatic) { Color.clear.frame(width: 0, height: 0) } }
        .onAppear { store.load() }
        .onChange(of: store.selectedPhoto) { _, newVal in
            if newVal != nil { openWindow(id: "viewer") }
        }
        .onKeyPress(.escape) {
            if store.isSelectMode {
                store.isSelectMode = false
                store.selectedPhotos.removeAll()
                return .handled
            }
            store.selectedPhoto = nil
            store.selectedIndex = -1
            return .handled
        }
        .onKeyPress("p") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.keepCurrent()
            return .handled
        }
        .onKeyPress("r") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.rejectCurrent()
            return .handled
        }
        .onKeyPress("u") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.unflagCurrent()
            return .handled
        }
    }
}

// MARK: - Viewer Window

struct ViewerWindow: View {
    @EnvironmentObject var store: PhotoStore

    var body: some View {
        Group {
            if let photo = store.selectedPhoto {
                DetailView(photo: photo)
                    .id(photo.id)
                    .transition(.opacity)
            } else {
                ZStack {
                    Color(nsColor: .controlBackgroundColor)
                    VStack(spacing: 8) {
                        Image(systemName: "photo.on.rectangle")
                            .font(.system(size: 40))
                            .foregroundColor(.secondary.opacity(0.3))
                        Text("Select a photo")
                            .font(.title3)
                            .foregroundColor(.secondary.opacity(0.5))
                    }
                }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: store.selectedPhoto?.id)
        .onKeyPress("p") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.keepCurrent()
            return .handled
        }
        .onKeyPress("r") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.rejectCurrent()
            return .handled
        }
        .onKeyPress("u") {
            guard store.selectedPhoto != nil else { return .ignored }
            store.unflagCurrent()
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
        .onKeyPress(.leftArrow) {
            store.moveToPrevious()
            return .handled
        }
        .onKeyPress(.rightArrow) {
            store.moveToNext()
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
                        if idx > 0 {
                            Text("\u{2229}")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.secondary.opacity(0.4))
                                .padding(.horizontal, 3)
                                .padding(.vertical, 2)
                                .background(
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(Color.primary.opacity(0.04))
                                )
                        }
                        ForEach(Array(group.chips.enumerated()), id: \.element.id) { chipIdx, chip in
                            if chipIdx > 0 {
                                Text(group.mode == .union ? "\u{222A}" : "\u{2229}")
                                    .font(.system(size: 7))
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
                                .font(.caption2)
                                .foregroundColor(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.accentColor.opacity(0.85)))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.horizontal, 10)
            }

            Spacer()

            Text("\(store.filteredPhotos.count)")
                .font(.caption)
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
        .frame(height: 28)
        .background(.bar)
    }
}

// MARK: - Grid Toolbar (bar above photos)

struct GridToolbar: View {
    @EnvironmentObject var store: PhotoStore

    var body: some View {
        let c = store.curationCounts
        HStack(spacing: 0) {
            // Left: count + curation pills
            Text("\(store.filteredPhotos.count)")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.primary)
                .padding(.leading, 12)

            Text("photos")
                .font(.system(size: 13))
                .foregroundColor(.secondary)
                .padding(.leading, 4)

            Spacer().frame(width: 16)

            // Curation filter pills
            HStack(spacing: 6) {
                CurationPill(label: "Picked", count: c.kept, color: .green, status: "kept",
                             icon: "checkmark.circle.fill")
                CurationPill(label: "Rejected", count: c.rejected, color: .red, status: "rejected",
                             icon: "xmark.circle.fill")
                CurationPill(label: "Unflagged", count: c.pending, color: .secondary, status: "pending",
                             icon: "circle")
            }

            // Reset button
            if store.filters.isActive {
                HoverButton {
                    store.clearFilters()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 11))
                        Text("Reset")
                            .font(.system(size: 12))
                    }
                    .foregroundColor(.secondary)
                }
                .padding(.leading, 8)
            }

            Spacer()

            // Batch actions (only when selecting)
            if store.isSelectMode && !store.selectedPhotos.isEmpty {
                HStack(spacing: 8) {
                    Text("\(store.selectedPhotos.count) selected")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.accentColor)
                    HoverButton { store.batchCurate(status: "kept") } label: {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 16))
                            .foregroundColor(.green)
                    }
                    HoverButton { store.batchCurate(status: "rejected") } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 16))
                            .foregroundColor(.red)
                    }
                    HoverButton { store.selectAll() } label: {
                        Text("All").font(.system(size: 12)).foregroundColor(.accentColor)
                    }
                }
                .padding(.trailing, 12)
            }

            // Right: sort + view controls
            HStack(spacing: 10) {
                // Sort
                Menu {
                    ForEach(SortOption.allCases, id: \.self) { option in
                        Button(action: { store.setSort(option) }) {
                            HStack {
                                Label(option.rawValue, systemImage: option.icon)
                                if store.sortBy == option {
                                    Image(systemName: store.sortDescending ? "chevron.down" : "chevron.up")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.system(size: 11))
                        Text(store.sortBy.rawValue)
                            .font(.system(size: 12))
                    }
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 5).fill(Color.primary.opacity(0.06)))
                }
                .menuStyle(.borderlessButton)
                .fixedSize()

                // Grid mode
                HoverIconButton(icon: store.squareCrop ? "square.grid.2x2" : "rectangle.grid.2x2",
                                color: .secondary) {
                    store.squareCrop.toggle()
                }

                // Select mode
                HoverIconButton(icon: store.isSelectMode ? "checkmark.circle.fill" : "checkmark.circle",
                                color: store.isSelectMode ? .accentColor : .secondary) {
                    store.toggleSelectMode()
                }
            }
            .padding(.trailing, 12)
        }
        .frame(height: 36)
        .background(Color.primary.opacity(0.04))
    }
}

// MARK: - Hover-aware button components

struct CurationPill: View {
    @EnvironmentObject var store: PhotoStore
    let label: String
    let count: Int
    let color: Color
    let status: String
    let icon: String
    @State private var isHovered = false

    var body: some View {
        let active = store.filters.curatedStatuses.contains(status)
        Button(action: { store.toggleFilter(\.curatedStatuses, status) }) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(active ? color : color.opacity(0.5))
                Text(label)
                    .font(.system(size: 12, weight: active ? .semibold : .regular))
                    .foregroundColor(active ? color : .secondary)
                Text("\(count)")
                    .font(.system(size: 11))
                    .foregroundColor(active ? color.opacity(0.7) : .secondary.opacity(0.5))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(active ? color.opacity(0.12) : isHovered ? Color.primary.opacity(0.06) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(active ? color.opacity(0.3) : isHovered ? Color.primary.opacity(0.1) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}

struct HoverButton<Label: View>: View {
    let action: () -> Void
    @ViewBuilder let label: Label
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            label
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isHovered ? Color.primary.opacity(0.1) : Color.primary.opacity(0.04))
                )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}

struct HoverIconButton: View {
    let icon: String
    let color: Color
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(color)
                .frame(width: 28, height: 28)
                .background(
                    RoundedRectangle(cornerRadius: 5)
                        .fill(isHovered ? Color.primary.opacity(0.1) : Color.clear)
                )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}
