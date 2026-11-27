fail <- function(message) stop(message, call. = FALSE)

require_package <- function(package) {
    if (!requireNamespace(package, quietly = TRUE))
        fail(paste("Required R package is missing:", package))
}

object <- function(x, allowed, label, required = character()) {
    if (!is.list(x) || length(x) && is.null(names(x)) ||
        anyDuplicated(names(x)) || any(!names(x) %in% allowed) ||
        any(!required %in% names(x)))
        fail(paste("Missing, unknown, or repeated fields in", label))
    x
}

vector_of <- function(x, type, label, length_min = 1L) {
    if (!is.list(x) || !is.null(names(x)) || length(x) < length_min ||
        !all(vapply(x, function(y) length(y) == 1L && !is.na(y) &&
            if (type == "text") is.character(y) && nzchar(y) else is.numeric(y) && is.finite(y),
            logical(1))))
        fail(paste("Expected an array of", type, "in", label))
    if (!length(x)) return(character())
    unlist(x, use.names = FALSE)
}

text <- function(x, label) {
    if (!is.character(x) || length(x) != 1L || is.na(x) || !nzchar(trimws(x)))
        fail(paste("Expected nonempty text in", label))
    x
}

limits <- function(x, label) {
    span <- vector_of(x, "numbers", label, 2L)
    if (length(span) != 2L || span[1] >= span[2]) fail(paste("Invalid range in", label))
    span
}

read_data <- function(path, sheet) {
    if (!is.null(sheet) && tolower(tools::file_ext(path)) != "xlsx")
        fail("sheet is only applicable to XLSX")
    switch(tolower(tools::file_ext(path)),
        csv = {
            input <- file(path, open = "rt", encoding = "UTF-8-BOM")
            on.exit(close(input))
            fields <- utils::count.fields(input, sep = ",", quote = "\"", comment.char = "")
            fields <- fields[!is.na(fields)]
            if (!length(fields) || any(fields != fields[1]))
                fail("CSV header and records must have the same number of fields")
            read.csv(path, colClasses = "character", check.names = FALSE,
                     fileEncoding = "UTF-8-BOM", na.strings = "", fill = FALSE)
        },
        xlsx = {
            require_package("readxl")
            if (!is.null(sheet)) text(sheet, "sheet")
            as.data.frame(readxl::read_xlsx(path, sheet = sheet, col_types = "text",
                                           .name_repair = "minimal"))
        },
        omv = {
            require_package("jmvReadWrite")
            jmvReadWrite::read_omv(path, useFlt = TRUE, rmMsVl = TRUE, sveAtt = FALSE)
        },
        fail("Dataset must be a CSV, XLSX, or OMV file"))
}

profile <- function(values, type, invalid = rep(FALSE, length(values))) {
    list(type = type, valid = sum(!is.na(values) & !invalid),
         missing = sum(is.na(values) & !invalid), invalid = sum(invalid))
}

prepare <- function(raw, columns) {
    if (!nrow(raw) || anyNA(names(raw)) || any(!nzchar(names(raw))) || anyDuplicated(names(raw)))
        fail("Dataset must have rows and nonempty, unique headers")
    object(columns, names(raw), "columns")
    data <- raw[, names(columns), drop = FALSE]
    checks <- list()
    for (name in names(data)) {
        rule <- object(columns[[name]], c("type", "missing", "range", "levels"), name, "type")
        type <- text(rule$type, paste(name, "type"))
        if (!type %in% c("continuous", "ordinal", "nominal", "text"))
            fail(paste("Unknown column type for", name))
        if (!is.null(rule$range) && type != "continuous")
            fail(paste("range can only be used on continuous columns:", name))
        if (!is.null(rule$levels) && !type %in% c("ordinal", "nominal"))
            fail(paste("levels can only be used on categorical columns:", name))
        values <- as.character(data[[name]])
        missing <- if (is.null(rule$missing)) character() else vector_of(rule$missing, "text", name, 0L)
        values[!is.na(values) & (!nzchar(trimws(values)) | values %in% missing)] <- NA_character_
        invalid <- rep(FALSE, length(values))
        if (type == "continuous") {
            numeric_values <- suppressWarnings(as.numeric(values))
            invalid <- !is.na(values) & !is.finite(numeric_values)
            if (!is.null(rule$range)) {
                span <- limits(rule$range, name)
                invalid <- invalid | (!is.na(numeric_values) &
                    (numeric_values < span[1] | numeric_values > span[2]))
            }
            values <- numeric_values
        } else if (type %in% c("ordinal", "nominal")) {
            if (is.null(rule$levels) && type == "ordinal") fail(paste("Supply ordered levels for", name))
            levels <- if (is.null(rule$levels)) sort(unique(stats::na.omit(values))) else
                vector_of(rule$levels, "text", paste(name, "levels"))
            if (anyDuplicated(levels)) fail(paste("Repeated levels for", name))
            invalid <- !is.na(values) & !values %in% levels
            values <- factor(values, levels = levels, ordered = type == "ordinal")
        }
        checks[[name]] <- profile(values, type, invalid)
        values[invalid] <- NA
        data[[name]] <- values
    }
    list(data = data, checks = checks)
}

numeric_items <- function(x, data, label, min = 1L) {
    items <- vector_of(x, "text", label, min)
    if (anyDuplicated(items) || !all(items %in% names(data)) ||
        !all(vapply(data[items], is.numeric, logical(1))))
        fail(paste("Use distinct, declared continuous items in", label))
    items
}

apply_scores <- function(prepared, scores, raw_names) {
    data <- prepared$data
    for (score in scores) {
        object(score, c("name", "items", "reverse", "range", "method", "min_answered"),
               "score", c("name", "items", "method", "min_answered"))
        name <- text(score$name, "score name")
        if (name %in% c(raw_names, names(data))) fail(paste("Score would overwrite a column:", name))
        items <- numeric_items(score$items, data[, intersect(raw_names, names(data)), drop = FALSE], name, 2L)
        reverse <- if (is.null(score$reverse)) character() else vector_of(score$reverse, "text", name, 0L)
        if (anyDuplicated(reverse) || !all(reverse %in% items)) fail(paste("Invalid reverse items for", name))
        required <- score$min_answered
        if (!is.numeric(required) || length(required) != 1L || !required %in% seq_along(items))
            fail(paste("min_answered must be an integer within the number of items for", name))
        method <- text(score$method, "score method")
        if (!method %in% c("sum", "mean") || (method == "sum" && required != length(items)))
            fail(paste("Use mean, or sum with all items required, for", name))
        values <- data[items]
        if (length(reverse)) {
            span <- limits(score$range, paste(name, "reverse-coding range"))
            if (any(vapply(values[reverse], function(v) any(v < span[1] | v > span[2], na.rm = TRUE),
                           logical(1))))
                fail(paste("Reverse-coded values are outside the specified range for", name))
            values[reverse] <- lapply(values[reverse], function(v) sum(span) - v)
        }
        total <- rowSums(values, na.rm = TRUE)
        answered <- rowSums(!is.na(values))
        if (method == "mean") total <- total / answered
        total[answered < required] <- NA_real_
        data[[name]] <- total
        prepared$checks[[name]] <- profile(total, "derived")
    }
    prepared$data <- data
    prepared
}

content_validity <- function(config, data) {
    object(config, c("items", "expert_id", "range", "relevant_at_least"), "cvi",
           c("items", "expert_id", "range", "relevant_at_least"))
    items <- numeric_items(config$items, data, "cvi.items")
    id <- text(config$expert_id, "cvi.expert_id")
    if (!id %in% names(data) || id %in% items || anyNA(data[[id]]) || anyDuplicated(data[[id]]))
        fail("CVI requires a separate declared ID with one nonmissing, unique row per expert")
    span <- limits(config$range, "cvi.range")
    cutoff <- config$relevant_at_least
    if (any(span != trunc(span)) || !is.numeric(cutoff) || length(cutoff) != 1L ||
        cutoff != trunc(cutoff) || cutoff <= span[1] || cutoff > span[2])
        fail("CVI requires an integer scale and a cutoff above its minimum and no higher than its maximum")
    if (nrow(data) < 2L) fail("CVI needs ratings from at least two experts")
    summary <- lapply(data[items], function(values) {
        if (any(values < span[1] | values > span[2] | values != trunc(values), na.rm = TRUE))
            fail("Expert ratings must be integers inside the declared scale")
        rated <- sum(!is.na(values))
        relevant <- sum(values >= cutoff, na.rm = TRUE)
        list(rated = rated, missing = length(values) - rated, relevant = relevant,
             i_cvi = if (rated >= 2L) relevant / rated else NA_real_)
    })
    complete <- all(vapply(summary, function(item) item$missing == 0L, logical(1)))
    indices <- vapply(summary, function(item) item$i_cvi, numeric(1))
    list(status = "ok", experts = nrow(data), relevant_at_least = cutoff, items = summary,
         s_cvi_ave = if (complete) mean(indices) else NA_real_,
         s_cvi_ua = if (complete) mean(indices == 1) else NA_real_)
}

# Preserve nested jamovi options (e.g. paired variables and regression blocks).
jmv_option <- function(value) {
    if (!is.list(value)) return(value)
    if (is.null(names(value)) && length(value) &&
        all(vapply(value, function(x) is.atomic(x) && length(x) == 1L, logical(1))) &&
        length(unique(vapply(value, typeof, ""))) == 1L)
        return(unlist(value, use.names = FALSE))
    lapply(value, jmv_option)
}

tables_from <- function(element, path = character()) {
    if (!isTRUE(element$visible)) return(list())
    if (identical(element$status, "error"))
        fail(paste(element$title, paste(unlist(element$state), collapse = " ")))
    if (inherits(element, "Table")) {
        values <- element$asDF
        if (!nrow(values)) return(list())
        rownames(values) <- NULL
        return(list(list(path = as.list(path), title = element$title,
                         columns = as.list(names(values)), rows = values,
                         notes = lapply(element$notes, function(note) note$note),
                         footnotes = as.list(element$footnotes))))
    }
    if (!inherits(element, c("Group", "Array"))) return(list())
    tables <- list()
    for (index in seq_along(element$itemNames)) {
        child <- if (inherits(element, "Array")) element$get(index = index) else
            element$get(element$itemNames[index])
        tables <- c(tables, tables_from(child, c(path, element$itemNames[index])))
    }
    tables
}

analyze <- function(request, data) {
    methods <- c("descriptives", "reliability", "ttestOneS", "ttestIS", "ttestPS",
                 "anovaOneW", "anovaNP", "anovaRM", "anovaRMNP", "ancova", "mancova",
                 "corrMatrix", "contTables", "contTablesPaired", "propTest2", "propTestN",
                 "linReg", "logRegBin", "logRegMulti", "logRegOrd", "pca", "efa", "cfa")
    method <- text(request$method, "analysis method")
    if (!method %in% methods) fail(paste("Unsupported jamovi method:", method))
    fun <- getExportedValue("jmv", method)
    options <- object(request$options, setdiff(names(formals(fun)), c("data", "formula")),
                      paste(request$id, "options"))
    n <- NULL
    if (method == "reliability") {
        vars <- numeric_items(options$vars, data, "reliability.vars", 2L)
        if (!is.null(options$revItems)) {
            reverse <- vector_of(options$revItems, "text", "reliability.revItems", 0L)
            if (anyDuplicated(reverse) || !all(reverse %in% vars)) fail("Invalid reliability reverse items")
        }
        data <- data[stats::complete.cases(data[vars]), , drop = FALSE]
        n <- nrow(data)
        if (n < 3L || any(vapply(data[vars], function(v) length(unique(v)) < 2L, logical(1))))
            fail("Reliability requires at least three complete rows and variation in every item")
    }
    warnings <- character()
    tables <- withCallingHandlers({
        result <- do.call(fun, c(list(data = data), lapply(options, jmv_option)))
        tables_from(result)
    }, warning = function(warning) {
        warnings <<- c(warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
    })
    if (!length(tables)) fail(paste("jamovi returned no visible tables:", request$id))
    list(status = "ok", complete_cases = n, tables = tables, warnings = as.list(unique(warnings)))
}

main <- function(args) {
    require_package("jsonlite")
    require_package("jmv")
    engine <- list(runtime = R.version.string, jmv = as.character(utils::packageVersion("jmv")))
    if (identical(args, "--version")) return(engine)
    if (length(args) != 2L) fail("Usage: jamovi-cli DATASET PLAN.json (or --version)")
    plan <- jsonlite::read_json(args[2])
    object(plan, c("columns", "analyses", "scores", "cvi", "sheet"), "plan", "columns")
    if (!length(plan$columns)) fail("Declare at least one dataset column in the plan")
    for (key in c("analyses", "scores")) {
        if (key %in% names(plan) && (!is.list(plan[[key]]) || !is.null(names(plan[[key]]))))
            fail(paste(key, "must be an array of objects"))
    }
    raw <- read_data(args[1], plan$sheet)
    prepared <- prepare(raw, plan$columns)
    invalid <- any(vapply(prepared$checks, function(x) x$invalid > 0L, logical(1)))
    blocked <- list(status = "blocked", reason = "Resolve invalid values before computing results")
    if (!invalid) prepared <- apply_scores(prepared, plan$scores, names(raw))
    ids <- vapply(plan$analyses, function(request) {
        object(request, c("id", "method", "options"), "analysis", c("id", "method", "options"))
        text(request$id, "analysis ID")
    }, "")
    if (anyDuplicated(ids)) fail("Analysis IDs must be unique")
    attempt <- function(expr) tryCatch(expr, error = function(e)
        list(status = "error", reason = conditionMessage(e)))
    analyses <- lapply(plan$analyses, function(request)
        c(list(id = request$id, method = request$method),
          if (invalid) blocked else attempt(analyze(request, prepared$data))))
    cvi <- if (!is.null(plan$cvi)) {
        if (invalid) blocked else attempt(content_validity(plan$cvi, prepared$data[names(plan$columns)]))
    }
    list(engine = engine, row_count = nrow(raw), profile = prepared$checks,
         analyses = analyses, cvi = cvi)
}

cat(jsonlite::toJSON(main(commandArgs(trailingOnly = TRUE)), auto_unbox = TRUE, null = "null",
                     na = "null", digits = NA, pretty = TRUE), "\n", sep = "")
