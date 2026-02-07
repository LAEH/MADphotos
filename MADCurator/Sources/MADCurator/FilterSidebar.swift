import SwiftUI

struct FilterSidebar: View {
    @EnvironmentObject var store: PhotoStore
    @FocusState private var searchFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                // Search
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                        .font(.system(size: 10))
                    TextField("Search...", text: $store.filters.searchText)
                        .textFieldStyle(.plain)
                        .font(.system(.caption, design: .monospaced))
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
                .padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))

                // Analysis (single-select)
                VStack(alignment: .leading, spacing: 6) {
                    sectionLabel("Analysis", icon: "sparkle.magnifyingglass")
                    FlowLayout(spacing: 4) {
                        let analyzed = store.allPhotos.filter { $0.isAnalyzed }.count
                        let notAnalyzed = store.allPhotos.count - analyzed
                        FilterChip(label: "Analyzed", count: analyzed,
                                   active: store.filters.analysisStatus == "analyzed") {
                            store.toggleAnalysis("analyzed")
                        }
                        if notAnalyzed > 0 {
                            FilterChip(label: "Not Analyzed", count: notAnalyzed,
                                       active: store.filters.analysisStatus == "pending") {
                                store.toggleAnalysis("pending")
                            }
                        }
                    }
                }

                // Curation
                facetSection("Curation", icon: "checkmark.circle", selected: store.filters.curatedStatuses,
                             options: store.options.curatedStatuses,
                             display: { $0.capitalized }) {
                    store.toggleFilter(\.curatedStatuses, $0)
                }

                // Category
                facetSection("Category", icon: "square.grid.2x2", selected: store.filters.categories,
                             options: store.options.categories) {
                    store.toggleFilter(\.categories, $0)
                }

                // Folder
                facetSection("Folder", icon: "folder", selected: store.filters.subcategories,
                             options: store.options.subcategories) {
                    store.toggleFilter(\.subcategories, $0)
                }

                // Orientation
                facetSection("Orientation", icon: "rectangle.portrait.and.arrow.right", selected: store.filters.orientations,
                             options: store.options.orientations,
                             display: { $0.capitalized }) {
                    store.toggleFilter(\.orientations, $0)
                }

                // Format
                facetSection("Format", icon: "doc", selected: store.filters.sourceFormats,
                             options: store.options.sourceFormats,
                             display: { $0.uppercased() }) {
                    store.toggleFilter(\.sourceFormats, $0)
                }

                // Camera
                facetSection("Camera", icon: "camera", selected: store.filters.cameras,
                             options: store.options.cameras) {
                    store.toggleFilter(\.cameras, $0)
                }

                // Location (NEW)
                facetSection("Location", icon: "mappin.and.ellipse", selected: store.filters.locations,
                             options: store.options.locations) {
                    store.toggleFilter(\.locations, $0)
                }

                // Grading
                facetSectionWithMode("Grading", icon: "paintpalette", dimension: .grading,
                             selected: store.filters.gradingStyles,
                             options: store.options.gradingStyles) {
                    store.toggleFilter(\.gradingStyles, $0)
                }

                // Vibe (with collapsible rare vibes)
                vibeSection

                // Style
                facetSectionWithMode("Style", icon: "theatermasks", dimension: .style,
                             selected: store.filters.styles,
                             options: store.options.styles) {
                    store.toggleFilter(\.styles, $0)
                }

                // Aesthetic
                facetSection("Aesthetic", icon: "star", selected: store.filters.aestheticBuckets,
                             options: store.options.aestheticBuckets) {
                    store.toggleFilter(\.aestheticBuckets, $0)
                }

                // Has Text
                hasTextSection

                // Time
                facetSectionWithMode("Time", icon: "clock", dimension: .time,
                             selected: store.filters.timesOfDay,
                             options: store.options.timesOfDay) {
                    store.toggleFilter(\.timesOfDay, $0)
                }

                // Setting
                facetSectionWithMode("Setting", icon: "mappin", dimension: .setting,
                             selected: store.filters.settings,
                             options: store.options.settings) {
                    store.toggleFilter(\.settings, $0)
                }

                // Weather
                facetSectionWithMode("Weather", icon: "cloud.sun", dimension: .weather,
                             selected: store.filters.weathers,
                             options: store.options.weathers) {
                    store.toggleFilter(\.weathers, $0)
                }

                // Scene
                facetSectionWithMode("Scene", icon: "mountain.2", dimension: .scene,
                             selected: store.filters.scenes,
                             options: store.options.scenes) {
                    store.toggleFilter(\.scenes, $0)
                }

                // Emotion
                facetSectionWithMode("Emotion", icon: "face.smiling", dimension: .emotion,
                             selected: store.filters.emotions,
                             options: store.options.emotions) {
                    store.toggleFilter(\.emotions, $0)
                }

                // Exposure
                facetSectionWithMode("Exposure", icon: "sun.max", dimension: .exposure,
                             selected: store.filters.exposures,
                             options: store.options.exposures) {
                    store.toggleFilter(\.exposures, $0)
                }

                // Depth
                facetSectionWithMode("Depth", icon: "cube", dimension: .depth,
                             selected: store.filters.depths,
                             options: store.options.depths) {
                    store.toggleFilter(\.depths, $0)
                }

                // Composition
                facetSectionWithMode("Composition", icon: "squareshape.split.3x3", dimension: .composition,
                             selected: store.filters.compositions,
                             options: store.options.compositions) {
                    store.toggleFilter(\.compositions, $0)
                }

                // Clear
                if store.filters.isActive {
                    Button("Clear All") { store.clearFilters() }
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundColor(.red)
                        .padding(.top, 4)
                }
            }
            .padding(12)
        }
        .background(.regularMaterial)
        .frame(minWidth: 200, idealWidth: 230, maxWidth: 280)
    }

    // MARK: - Reusable section

    @ViewBuilder
    private func facetSection(_ title: String, icon: String, selected: Set<String>,
                              options: [FacetOption],
                              display: @escaping (String) -> String = { $0 },
                              toggle: @escaping (String) -> Void) -> some View {
        if !options.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 4) {
                    sectionLabel(title, icon: icon, hasActive: !selected.isEmpty)
                    if !selected.isEmpty {
                        Text("·\(selected.count)")
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundColor(.accentColor)
                    }
                }
                FlowLayout(spacing: 4) {
                    ForEach(options) { opt in
                        FilterChip(label: display(opt.value), count: opt.count,
                                   active: selected.contains(opt.value)) {
                            toggle(opt.value)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Facet section with mode toggle

    @ViewBuilder
    private func facetSectionWithMode(_ title: String, icon: String,
                                       dimension: FilterDimension,
                                       selected: Set<String>,
                                       options: [FacetOption],
                                       display: @escaping (String) -> String = { $0 },
                                       toggle: @escaping (String) -> Void) -> some View {
        if !options.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 4) {
                    sectionLabel(title, icon: icon, hasActive: !selected.isEmpty)
                    if !selected.isEmpty {
                        Text("·\(selected.count)")
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundColor(.accentColor)
                    }
                    Spacer()
                    if selected.count >= 2 {
                        HStack(spacing: 0) {
                            modeButton("Any", mode: .union, dim: dimension)
                            modeButton("All", mode: .intersection, dim: dimension)
                        }
                        .background(RoundedRectangle(cornerRadius: 3).fill(Color.primary.opacity(0.06)))
                    }
                }
                FlowLayout(spacing: 4) {
                    ForEach(options) { opt in
                        FilterChip(label: display(opt.value), count: opt.count,
                                   active: selected.contains(opt.value)) {
                            toggle(opt.value)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Has Text section

    @ViewBuilder
    private var hasTextSection: some View {
        let withText = store.allPhotos.filter { $0.hasOCRText }.count
        let withoutText = store.allPhotos.count - withText
        if withText > 0 {
            VStack(alignment: .leading, spacing: 6) {
                sectionLabel("Text (OCR)", icon: "text.viewfinder", hasActive: store.filters.hasTextFilter != nil)
                FlowLayout(spacing: 4) {
                    FilterChip(label: "Has Text", count: withText,
                               active: store.filters.hasTextFilter == "yes") {
                        store.toggleHasText("yes")
                    }
                    FilterChip(label: "No Text", count: withoutText,
                               active: store.filters.hasTextFilter == "no") {
                        store.toggleHasText("no")
                    }
                }
            }
        }
    }

    // MARK: - Vibe section (with Any/All toggle + collapsible rare vibes)

    @State private var showAllVibes = false
    private let vibeMinCount = 5

    @ViewBuilder
    private var vibeSection: some View {
        if !store.options.vibes.isEmpty {
            let top = store.options.vibes.filter { $0.count >= vibeMinCount }
            let rest = store.options.vibes.filter { $0.count < vibeMinCount }

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 4) {
                    sectionLabel("Vibe", icon: "sparkles", hasActive: !store.filters.vibes.isEmpty)
                    if !store.filters.vibes.isEmpty {
                        Text("·\(store.filters.vibes.count)")
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundColor(.accentColor)
                    }
                    Spacer()
                    if store.filters.vibes.count >= 2 {
                        HStack(spacing: 0) {
                            modeButton("Any", mode: .union, dim: .vibe)
                            modeButton("All", mode: .intersection, dim: .vibe)
                        }
                        .background(RoundedRectangle(cornerRadius: 3).fill(Color.primary.opacity(0.06)))
                    }
                }
                FlowLayout(spacing: 4) {
                    ForEach(top) { opt in
                        FilterChip(label: opt.value, count: opt.count,
                                   active: store.filters.vibes.contains(opt.value)) {
                            store.toggleFilter(\.vibes, opt.value)
                        }
                    }
                }
                if !rest.isEmpty {
                    Button(action: { withAnimation(.easeInOut(duration: 0.2)) { showAllVibes.toggle() } }) {
                        HStack(spacing: 3) {
                            Text(showAllVibes ? "fewer" : "all \(rest.count) more")
                            Image(systemName: showAllVibes ? "chevron.up" : "chevron.down")
                                .font(.system(size: 7))
                        }
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)

                    if showAllVibes {
                        FlowLayout(spacing: 4) {
                            ForEach(rest) { opt in
                                FilterChip(label: opt.value, count: opt.count,
                                           active: store.filters.vibes.contains(opt.value)) {
                                    store.toggleFilter(\.vibes, opt.value)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private func modeButton(_ label: String, mode: QueryMode, dim: FilterDimension) -> some View {
        Button(action: { store.setMode(mode, for: dim) }) {
            Text(label)
                .font(.system(.caption2, design: .monospaced))
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(store.filters.mode(for: dim) == mode ? Color.accentColor : Color.clear)
                .foregroundColor(store.filters.mode(for: dim) == mode ? .white : .secondary)
                .cornerRadius(3)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    @ViewBuilder
    private func sectionLabel(_ title: String, icon: String? = nil, hasActive: Bool = false) -> some View {
        HStack(spacing: 4) {
            if let icon = icon {
                Image(systemName: icon)
                    .font(.system(size: 9))
                    .foregroundColor(hasActive ? .accentColor : .secondary)
            }
            Text(title.uppercased())
                .font(.system(.caption2, design: .monospaced))
                .fontWeight(.bold)
                .foregroundColor(.secondary)
                .kerning(1)
            if hasActive {
                Circle()
                    .fill(Color.accentColor)
                    .frame(width: 4, height: 4)
            }
        }
    }
}

// MARK: - Filter Chip

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
            .font(.system(.caption2, design: .monospaced))
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
