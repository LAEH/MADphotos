import SwiftUI

struct FilterSidebar: View {
    @EnvironmentObject var store: PhotoStore
    @FocusState private var searchFocused: Bool

    @State private var expanded: Set<String> = [
        "camera", "orientation", "style", "scene"
    ]
    @State private var showAll: Set<String> = []

    private let topN = 8

    var body: some View {
        ScrollView(.vertical, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 0) {
                // Search
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                        .font(.system(size: 10))
                    TextField("Search...", text: $store.filters.searchText)
                        .textFieldStyle(.plain)
                        .font(.caption)
                        .focused($searchFocused)
                        .onChange(of: store.filters.searchText) { store.applyFilters() }
                    if !store.filters.searchText.isEmpty {
                        Button {
                            store.filters.searchText = ""
                            store.applyFilters()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary.opacity(0.6))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 5).fill(Color.primary.opacity(0.05)))
                .padding(.horizontal, 10)
                .padding(.top, 10)
                .padding(.bottom, 4)

                // ── Quick toggles ──
                quickToggleSection

                Divider().padding(.horizontal, 10).padding(.vertical, 4)

                // ── Primary ──
                listSection("camera", title: "Camera", icon: "camera",
                            selected: store.filters.cameras,
                            options: store.options.cameras) {
                    store.toggleFilter(\.cameras, $0)
                }

                listSection("orientation", title: "Orientation", icon: "rectangle.portrait.and.arrow.right",
                            selected: store.filters.orientations,
                            options: store.options.orientations,
                            display: { $0.capitalized }) {
                    store.toggleFilter(\.orientations, $0)
                }

                listSection("style", title: "Style", icon: "theatermasks",
                            selected: store.filters.styles,
                            options: store.options.styles) {
                    store.toggleFilter(\.styles, $0)
                }

                listSection("scene", title: "Scene", icon: "mountain.2",
                            selected: store.filters.scenes,
                            options: store.options.scenes) {
                    store.toggleFilter(\.scenes, $0)
                }

                listSection("category", title: "Category", icon: "square.grid.2x2",
                            selected: store.filters.categories,
                            options: store.options.categories) {
                    store.toggleFilter(\.categories, $0)
                }

                listSection("aesthetic", title: "Aesthetic", icon: "star",
                            selected: store.filters.aestheticBuckets,
                            options: store.options.aestheticBuckets) {
                    store.toggleFilter(\.aestheticBuckets, $0)
                }

                Divider().padding(.horizontal, 10).padding(.vertical, 4)

                // ── Classification ──
                listSection("vibe", title: "Vibe", icon: "sparkles",
                            selected: store.filters.vibes,
                            options: store.options.vibes) {
                    store.toggleFilter(\.vibes, $0)
                }

                listSection("emotion", title: "Emotion", icon: "face.smiling",
                            selected: store.filters.emotions,
                            options: store.options.emotions) {
                    store.toggleFilter(\.emotions, $0)
                }

                listSection("grading", title: "Grading", icon: "paintpalette",
                            selected: store.filters.gradingStyles,
                            options: store.options.gradingStyles) {
                    store.toggleFilter(\.gradingStyles, $0)
                }

                listSection("setting", title: "Setting", icon: "mappin",
                            selected: store.filters.settings,
                            options: store.options.settings) {
                    store.toggleFilter(\.settings, $0)
                }

                listSection("weather", title: "Weather", icon: "cloud.sun",
                            selected: store.filters.weathers,
                            options: store.options.weathers) {
                    store.toggleFilter(\.weathers, $0)
                }

                listSection("time", title: "Time", icon: "clock",
                            selected: store.filters.timesOfDay,
                            options: store.options.timesOfDay) {
                    store.toggleFilter(\.timesOfDay, $0)
                }

                Divider().padding(.horizontal, 10).padding(.vertical, 4)

                // ── Technical ──
                listSection("exposure", title: "Exposure", icon: "sun.max",
                            selected: store.filters.exposures,
                            options: store.options.exposures) {
                    store.toggleFilter(\.exposures, $0)
                }

                listSection("depth", title: "Depth", icon: "cube",
                            selected: store.filters.depths,
                            options: store.options.depths) {
                    store.toggleFilter(\.depths, $0)
                }

                listSection("composition", title: "Composition", icon: "squareshape.split.3x3",
                            selected: store.filters.compositions,
                            options: store.options.compositions) {
                    store.toggleFilter(\.compositions, $0)
                }

                listSection("medium", title: "Medium", icon: "film",
                            selected: store.filters.mediums,
                            options: store.options.mediums,
                            display: { $0.replacingOccurrences(of: "_", with: " ").capitalized }) {
                    store.toggleFilter(\.mediums, $0)
                }

                listSection("filmStock", title: "Film Stock", icon: "film.stack",
                            selected: store.filters.filmStocks,
                            options: store.options.filmStocks) {
                    store.toggleFilter(\.filmStocks, $0)
                }

                listSection("format", title: "Format", icon: "doc",
                            selected: store.filters.sourceFormats,
                            options: store.options.sourceFormats,
                            display: { $0.uppercased() }) {
                    store.toggleFilter(\.sourceFormats, $0)
                }

                listSection("folder", title: "Folder", icon: "folder",
                            selected: store.filters.subcategories,
                            options: store.options.subcategories) {
                    store.toggleFilter(\.subcategories, $0)
                }

                listSection("curation", title: "Curation", icon: "checkmark.circle",
                            selected: store.filters.curatedStatuses,
                            options: store.options.curatedStatuses,
                            display: { $0.capitalized }) {
                    store.toggleFilter(\.curatedStatuses, $0)
                }

                Divider().padding(.horizontal, 10).padding(.vertical, 4)

                listSection("enhancement", title: "Enhancement", icon: "wand.and.stars",
                            selected: store.filters.enhancements,
                            options: store.options.enhancements,
                            display: { $0.capitalized }) {
                    store.toggleFilter(\.enhancements, $0)
                }

                listSection("location", title: "Location", icon: "mappin.and.ellipse",
                            selected: store.filters.locations,
                            options: store.options.locations) {
                    store.toggleFilter(\.locations, $0)
                }

                // Clear all
                if store.filters.isActive {
                    Button("Clear All") { store.clearFilters() }
                        .font(.caption2)
                        .foregroundColor(.red)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                }

                Spacer().frame(height: 20)
            }
        }
        .background(.regularMaterial)
        .frame(minWidth: 180, idealWidth: 220, maxWidth: 260)
    }

    // MARK: - Quick toggles (Analysis, Color, OCR — always visible, compact)

    private var quickToggleSection: some View {
        let qc = store.quickCounts
        return VStack(alignment: .leading, spacing: 2) {
            // Subject
            quickRow("People", count: qc.people, icon: "person.fill",
                     active: store.filters.subjectFilter == "people") {
                store.toggleSubject("people")
            }
            quickRow("Animals", count: qc.animals, icon: "pawprint.fill",
                     active: store.filters.subjectFilter == "animal") {
                store.toggleSubject("animal")
            }
            quickRow("No Subject", count: qc.noSubject, icon: "mountain.2",
                     active: store.filters.subjectFilter == "none") {
                store.toggleSubject("none")
            }

            Divider().padding(.horizontal, 12).padding(.vertical, 2)

            // Color
            if qc.monochrome > 0 {
                quickRow("Monochrome", count: qc.monochrome, icon: "circle.lefthalf.filled",
                         active: store.filters.monochromeFilter == "yes") {
                    store.toggleMonochrome("yes")
                }
                quickRow("Color", count: qc.color, icon: "circle.righthalf.filled",
                         active: store.filters.monochromeFilter == "no") {
                    store.toggleMonochrome("no")
                }
            }

            if qc.withText > 0 {
                quickRow("Has Text", count: qc.withText, icon: "text.viewfinder",
                         active: store.filters.hasTextFilter == "yes") {
                    store.toggleHasText("yes")
                }
            }
        }
    }

    private func quickRow(_ label: String, count: Int, icon: String,
                          active: Bool, action: @escaping () -> Void) -> some View {
        SidebarRow(label: label, count: count, icon: icon, active: active, action: action)
    }

    // MARK: - List section (collapsible, capped, compact rows)

    @ViewBuilder
    private func listSection(
        _ key: String, title: String, icon: String,
        selected: Set<String>, options: [FacetOption],
        display: @escaping (String) -> String = { $0 },
        toggle: @escaping (String) -> Void
    ) -> some View {
        if !options.isEmpty {
            let isOpen = expanded.contains(key)
            let sorted = options.sorted { $0.count > $1.count }
            let isShowingAll = showAll.contains(key)
            let visible = isShowingAll ? sorted : Array(sorted.prefix(topN))
            let remaining = sorted.count - topN

            VStack(alignment: .leading, spacing: 0) {
                // Header
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        if expanded.contains(key) {
                            expanded.remove(key)
                        } else {
                            expanded.insert(key)
                        }
                    }
                }) {
                    HStack(spacing: 5) {
                        Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                            .font(.system(size: 7, weight: .bold))
                            .foregroundColor(.secondary.opacity(0.4))
                            .frame(width: 8)
                        Image(systemName: icon)
                            .font(.system(size: 9))
                            .foregroundColor(!selected.isEmpty ? .accentColor : .secondary)
                        Text(title.uppercased())
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .foregroundColor(.secondary)
                            .kerning(0.8)
                        if !selected.isEmpty {
                            Text("\(selected.count)")
                                .font(.caption2)
                                .fontWeight(.bold)
                                .foregroundColor(.accentColor)
                        }
                        Spacer()
                        if !isOpen {
                            Text("\(options.count)")
                                .font(.caption2)
                                .foregroundColor(.secondary.opacity(0.3))
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                // Items
                if isOpen {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(visible) { opt in
                            filterRow(display(opt.value), count: opt.count,
                                      active: selected.contains(opt.value)) {
                                toggle(opt.value)
                            }
                        }
                        if remaining > 0 && !isShowingAll {
                            Button(action: {
                                withAnimation(.easeInOut(duration: 0.15)) {
                                    _ = showAll.insert(key)
                                }
                            }) {
                                HStack(spacing: 4) {
                                    Text("+\(remaining) more")
                                    Image(systemName: "chevron.down")
                                        .font(.system(size: 6))
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary.opacity(0.6))
                                .padding(.leading, 30)
                                .padding(.vertical, 3)
                            }
                            .buttonStyle(.plain)
                        } else if isShowingAll && remaining > 0 {
                            Button(action: {
                                withAnimation(.easeInOut(duration: 0.15)) {
                                    _ = showAll.remove(key)
                                }
                            }) {
                                HStack(spacing: 4) {
                                    Text("fewer")
                                    Image(systemName: "chevron.up")
                                        .font(.system(size: 6))
                                }
                                .font(.caption2)
                                .foregroundColor(.secondary.opacity(0.6))
                                .padding(.leading, 30)
                                .padding(.vertical, 3)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.bottom, 4)
                }
            }
        }
    }

    // MARK: - Filter row

    private func filterRow(_ label: String, count: Int, active: Bool,
                           action: @escaping () -> Void) -> some View {
        SidebarFilterRow(label: label, count: count, active: active, action: action)
    }
}

// MARK: - Hover-aware sidebar rows

struct SidebarRow: View {
    let label: String
    let count: Int
    let icon: String
    let active: Bool
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 9))
                    .foregroundColor(active ? .accentColor : .secondary)
                    .frame(width: 12)
                Text(label)
                    .font(.caption2)
                    .foregroundColor(active ? .accentColor : .primary)
                Spacer()
                Text("\(count)")
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 3)
            .background(active ? Color.accentColor.opacity(0.1) : isHovered ? Color.primary.opacity(0.06) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}

struct SidebarFilterRow: View {
    let label: String
    let count: Int
    let active: Bool
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 0) {
                Text(label)
                    .font(.caption2)
                    .foregroundColor(active ? .white : .primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 4)
                Text("\(count)")
                    .font(.caption2)
                    .foregroundColor(active ? .white.opacity(0.7) : .secondary.opacity(0.5))
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2.5)
            .background(
                RoundedRectangle(cornerRadius: 3)
                    .fill(active ? Color.accentColor : isHovered ? Color.primary.opacity(0.08) : Color.clear)
            )
            .padding(.leading, 28)
            .padding(.trailing, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}

// MARK: - Filter Chip (still used by QueryBar)

struct FilterChip: View {
    let label: String
    let count: Int
    let active: Bool
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 0) {
                Text(label)
                Text("·\(count)")
                    .foregroundColor(active ? .white.opacity(0.55) : .secondary)
            }
            .font(.caption2)
            .lineLimit(1)
            .foregroundColor(active ? .white : .primary)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(active ? Color.accentColor :
                            isHovered ? Color.primary.opacity(0.1) : Color.primary.opacity(0.06))
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}
