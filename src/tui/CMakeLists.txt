#
# CMakeLists.txt for RStudio TUI
#
# This file integrates the Python-based TUI with the RStudio build system.
#

cmake_minimum_required(VERSION 3.16)

project(rstudio-tui VERSION 0.1.0 LANGUAGES NONE)

# Find Python
find_package(Python3 COMPONENTS Interpreter REQUIRED)

# Option to build TUI
option(RSTUDIO_BUILD_TUI "Build the Terminal User Interface" ON)

if(RSTUDIO_BUILD_TUI)
    message(STATUS "RStudio TUI build enabled")

    # Create virtual environment and install dependencies
    set(TUI_VENV_DIR "${CMAKE_CURRENT_BINARY_DIR}/venv")
    set(TUI_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")

    # Custom target to create virtual environment
    add_custom_target(rstudio-tui-venv
        COMMAND ${Python3_EXECUTABLE} -m venv "${TUI_VENV_DIR}"
        COMMENT "Creating Python virtual environment for TUI"
    )

    # Custom target to install TUI package
    add_custom_target(rstudio-tui-install
        COMMAND "${TUI_VENV_DIR}/bin/pip" install -e "${TUI_SOURCE_DIR}"
        DEPENDS rstudio-tui-venv
        COMMENT "Installing RStudio TUI package"
    )

    # Main TUI target
    add_custom_target(rstudio-tui ALL
        DEPENDS rstudio-tui-install
        COMMENT "Building RStudio TUI"
    )

    # Installation
    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/scripts/rstudio-tui"
        DESTINATION bin
        PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE
    )

    if(WIN32)
        install(
            FILES "${CMAKE_CURRENT_SOURCE_DIR}/scripts/rstudio-tui.cmd"
            DESTINATION bin
        )
    endif()

    # Install Python package
    install(
        DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/rstudio_tui"
        DESTINATION lib/rstudio-tui
    )

    install(
        FILES "${CMAKE_CURRENT_SOURCE_DIR}/pyproject.toml"
        DESTINATION lib/rstudio-tui
    )

    # Test target
    add_custom_target(rstudio-tui-test
        COMMAND "${TUI_VENV_DIR}/bin/python" -m pytest "${TUI_SOURCE_DIR}/tests" -v
        DEPENDS rstudio-tui-install
        COMMENT "Running RStudio TUI tests"
    )

endif()
